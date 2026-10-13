//! LoopRail `Session` PDA: a fixed-size, auditable metered session.
//!
//! One session is one zero-copy PDA with a bounded provider table (`channels[N]`)
//! and a step ring buffer (`steps[K]`). `record_step` executes on the MagicBlock
//! Ephemeral Rollup (fast, free, NOT a commit); `checkpoint` and
//! `close_and_undelegate` are the only operations that consume a commit nonce.
//! See `docs/adr/ADR-3-pda-model.md`.

use anchor_lang::prelude::*;
use ephemeral_rollups_sdk::anchor::{commit, delegate, ephemeral};
use ephemeral_rollups_sdk::cpi::DelegateConfig;
use ephemeral_rollups_sdk::ephem::MagicIntentBundleBuilder;

declare_id!("Eidxr4sVDqni1pTjLgKZFXVXTTP84fm6GNpHZRbWXFh6");

pub const SESSION_SEED: &[u8] = b"session";

/// Maximum providers per session (ADR-3: `channels[N]`).
pub const MAX_CHANNELS: usize = 8;
/// Step ring-buffer capacity (ADR-3: `steps[K]`); covers the 50-step demo with headroom.
pub const RING_CAPACITY: usize = 64;
/// At most two `checkpoint`s plus one terminal `close_and_undelegate`.
pub const MAX_CHECKPOINTS: u8 = 2;

pub const STATUS_OPEN: u8 = 0;
pub const STATUS_CLOSED: u8 = 1;
pub const STATUS_ABORTED: u8 = 2;

pub const OUTCOME_OK: u8 = 0;
pub const OUTCOME_ERROR: u8 = 1;
pub const OUTCOME_TIMEOUT: u8 = 2;
pub const OUTCOME_DENIED: u8 = 3;

#[ephemeral]
#[program]
pub mod looprail_session {
    use super::*;

    /// Create the fixed-size session PDA on the base layer.
    #[allow(clippy::too_many_arguments)]
    pub fn init_session(
        ctx: Context<InitSession>,
        session_id: [u8; 32],
        policy_hash: [u8; 32],
        authority: Pubkey,
        budget_total: u64,
        providers: Vec<Pubkey>,
        allocations: Vec<u64>,
    ) -> Result<()> {
        require!(budget_total > 0, LoopRailError::InvalidBudget);
        require!(
            providers.len() == allocations.len(),
            LoopRailError::ChannelConfigMismatch
        );
        require!(providers.len() <= MAX_CHANNELS, LoopRailError::ChannelsFull);

        let mut allocated: u64 = 0;
        for allocation in allocations.iter() {
            allocated = allocated
                .checked_add(*allocation)
                .ok_or(LoopRailError::InvalidBudget)?;
        }
        require!(allocated <= budget_total, LoopRailError::InvalidBudget);

        let session_key = ctx.accounts.session.key();
        let mut session = ctx.accounts.session.load_init()?;
        session.owner = ctx.accounts.owner.key();
        session.authority = authority;
        session.session_id = session_id;
        session.policy_hash = policy_hash;
        session.budget_total = budget_total;
        session.spent = 0;
        session.reserved = 0;
        session.step_count = 0;
        session.status = STATUS_OPEN;
        session.opened_at = Clock::get()?.unix_timestamp;
        session.closed_at = 0;
        session.channel_count = providers.len() as u8;
        session.checkpoint_count = 0;
        session.bump = ctx.bumps.session;

        for (i, provider) in providers.iter().enumerate() {
            session.channels[i] = Channel {
                provider: *provider,
                allocation: allocations[i],
                spent: 0,
            };
        }

        emit!(SessionInitialized {
            session: session_key,
            owner: ctx.accounts.owner.key(),
            authority,
            budget_total,
            channel_count: providers.len() as u8,
        });
        Ok(())
    }

    /// Delegate the session PDA to the Ephemeral Rollup.
    /// The ER validator is taken from the first `remaining_accounts` entry.
    pub fn delegate_session(ctx: Context<DelegateSession>, session_id: [u8; 32]) -> Result<()> {
        ctx.accounts.delegate_session(
            &ctx.accounts.owner,
            &[
                SESSION_SEED,
                ctx.accounts.owner.key().as_ref(),
                session_id.as_ref(),
            ],
            DelegateConfig {
                validator: ctx.remaining_accounts.first().map(|acc| acc.key()),
                ..Default::default()
            },
        )?;
        Ok(())
    }

    /// Append a step to the ring buffer on the ER. Free and NOT a commit.
    ///
    /// `step_idx` must be strictly monotonic (`== step_count`): the ER drops
    /// identical transactions, so monotonicity both orders the log and keeps
    /// consecutive ER txs distinct.
    #[allow(clippy::too_many_arguments)]
    pub fn record_step(
        ctx: Context<RecordStep>,
        _owner: Pubkey,
        _session_id: [u8; 32],
        step_idx: u32,
        tool_idx: u8,
        provider_idx: u8,
        cost: u64,
        latency_ms: u32,
        outcome: u8,
        cache_hit: bool,
    ) -> Result<()> {
        let session_key = ctx.accounts.session.key();
        let mut session = ctx.accounts.session.load_mut()?;
        require!(
            ctx.accounts.authority.key() == session.authority,
            LoopRailError::Unauthorized
        );
        require!(session.status == STATUS_OPEN, LoopRailError::SessionNotOpen);
        require!(
            step_idx == session.step_count,
            LoopRailError::OutOfOrderStep
        );
        require!(
            (provider_idx as usize) < session.channel_count as usize,
            LoopRailError::ProviderIndexOutOfRange
        );
        require!(outcome <= OUTCOME_DENIED, LoopRailError::InvalidOutcome);
        require!(!cache_hit || cost == 0, LoopRailError::CacheHitMustBeFree);

        let new_spent = session
            .spent
            .checked_add(cost)
            .ok_or(LoopRailError::BudgetExceeded)?;
        require!(new_spent <= session.budget_total, LoopRailError::BudgetExceeded);

        let channel = &mut session.channels[provider_idx as usize];
        let channel_spent = channel
            .spent
            .checked_add(cost)
            .ok_or(LoopRailError::BudgetExceeded)?;
        require!(
            channel_spent <= channel.allocation,
            LoopRailError::ChannelAllocationExceeded
        );

        channel.spent = channel_spent;
        session.spent = new_spent;
        let ring_idx = (session.step_count as usize) % RING_CAPACITY;
        session.steps[ring_idx] = StepEntry {
            step_idx,
            tool_idx,
            provider_idx,
            outcome,
            cache_hit: cache_hit as u8,
            cost,
            latency_ms,
            reserved: 0,
        };
        session.step_count = session
            .step_count
            .checked_add(1)
            .ok_or(LoopRailError::InvalidBudget)?;

        emit!(StepRecorded {
            session: session_key,
            step_idx,
            provider_idx,
            cost,
            spent: new_spent,
        });
        Ok(())
    }

    /// Commit the session state to the base layer (consumes one commit nonce).
    pub fn checkpoint(ctx: Context<Checkpoint>, _owner: Pubkey, _session_id: [u8; 32]) -> Result<()> {
        let session_info = ctx.accounts.session.to_account_info();
        let session_key = ctx.accounts.session.key();
        let mut session = ctx.accounts.session.load_mut()?;
        require!(session.status == STATUS_OPEN, LoopRailError::SessionNotOpen);
        require!(
            session.checkpoint_count < MAX_CHECKPOINTS,
            LoopRailError::TooManyCheckpoints
        );

        session.checkpoint_count += 1;
        let checkpoint_count = session.checkpoint_count;
        let step_count = session.step_count;
        drop(session);

        emit!(Checkpointed {
            session: session_key,
            checkpoint_count,
            step_count,
        });

        MagicIntentBundleBuilder::new(
            ctx.accounts.payer.to_account_info(),
            ctx.accounts.magic_context.to_account_info(),
            ctx.accounts.magic_program.to_account_info(),
        )
        .commit(&[session_info])
        .build_and_invoke()?;

        Ok(())
    }

    /// Terminal commit + undelegate. Ends the session and returns it to the base layer.
    pub fn close_and_undelegate(
        ctx: Context<Checkpoint>,
        _owner: Pubkey,
        _session_id: [u8; 32],
    ) -> Result<()> {
        let session_info = ctx.accounts.session.to_account_info();
        let session_key = ctx.accounts.session.key();
        let mut session = ctx.accounts.session.load_mut()?;
        require!(
            session.status == STATUS_OPEN || session.status == STATUS_ABORTED,
            LoopRailError::InvalidStatus
        );
        session.status = STATUS_CLOSED;
        session.closed_at = Clock::get()?.unix_timestamp;
        let step_count = session.step_count;
        let spent = session.spent;
        drop(session);

        MagicIntentBundleBuilder::new(
            ctx.accounts.payer.to_account_info(),
            ctx.accounts.magic_context.to_account_info(),
            ctx.accounts.magic_program.to_account_info(),
        )
        .commit_and_undelegate(&[session_info])
        .build_and_invoke()?;

        emit!(SessionClosed {
            session: session_key,
            step_count,
            spent,
        });
        Ok(())
    }

    /// Kill switch. Owner or authority aborts an open session; the account is
    /// kept for audit. A delegated session is released with `close_and_undelegate`.
    pub fn abort(ctx: Context<Abort>, _owner: Pubkey, _session_id: [u8; 32]) -> Result<()> {
        let session_key = ctx.accounts.session.key();
        let mut session = ctx.accounts.session.load_mut()?;
        let signer = ctx.accounts.signer.key();
        require!(
            signer == session.owner || signer == session.authority,
            LoopRailError::Unauthorized
        );
        require!(session.status == STATUS_OPEN, LoopRailError::SessionNotOpen);

        session.status = STATUS_ABORTED;
        session.closed_at = Clock::get()?.unix_timestamp;
        let step_count = session.step_count;
        drop(session);

        emit!(SessionAborted {
            session: session_key,
            step_count,
        });
        Ok(())
    }
}

#[derive(Accounts)]
#[instruction(session_id: [u8; 32])]
pub struct InitSession<'info> {
    #[account(
        init,
        payer = owner,
        space = 8 + std::mem::size_of::<Session>(),
        seeds = [SESSION_SEED, owner.key().as_ref(), session_id.as_ref()],
        bump,
    )]
    pub session: AccountLoader<'info, Session>,
    #[account(mut)]
    pub owner: Signer<'info>,
    pub system_program: Program<'info, System>,
}

/// Adds the delegation helper to the context (`delegate_session`).
#[delegate]
#[derive(Accounts)]
#[instruction(session_id: [u8; 32])]
pub struct DelegateSession<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,
    /// CHECK: PDA to delegate, validated by its seeds.
    #[account(mut, del, seeds = [SESSION_SEED, owner.key().as_ref(), session_id.as_ref()], bump)]
    pub session: UncheckedAccount<'info>,
}

#[derive(Accounts)]
#[instruction(owner: Pubkey, session_id: [u8; 32])]
pub struct RecordStep<'info> {
    #[account(mut, seeds = [SESSION_SEED, owner.as_ref(), session_id.as_ref()], bump)]
    pub session: AccountLoader<'info, Session>,
    pub authority: Signer<'info>,
}

#[commit]
#[derive(Accounts)]
#[instruction(owner: Pubkey, session_id: [u8; 32])]
pub struct Checkpoint<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,
    #[account(mut, seeds = [SESSION_SEED, owner.as_ref(), session_id.as_ref()], bump)]
    pub session: AccountLoader<'info, Session>,
}

#[derive(Accounts)]
#[instruction(owner: Pubkey, session_id: [u8; 32])]
pub struct Abort<'info> {
    pub signer: Signer<'info>,
    #[account(mut, seeds = [SESSION_SEED, owner.as_ref(), session_id.as_ref()], bump)]
    pub session: AccountLoader<'info, Session>,
}

#[account(zero_copy)]
pub struct Session {
    pub owner: Pubkey,
    pub authority: Pubkey,
    pub session_id: [u8; 32],
    pub policy_hash: [u8; 32],
    pub budget_total: u64,
    pub spent: u64,
    pub reserved: u64,
    pub step_count: u32,
    pub status: u8,
    pub channel_count: u8,
    pub checkpoint_count: u8,
    pub bump: u8,
    pub opened_at: i64,
    pub closed_at: i64,
    pub channels: [Channel; MAX_CHANNELS],
    pub steps: [StepEntry; RING_CAPACITY],
}

#[zero_copy]
pub struct Channel {
    pub provider: Pubkey,
    pub allocation: u64,
    pub spent: u64,
}

#[zero_copy]
pub struct StepEntry {
    pub step_idx: u32,
    pub tool_idx: u8,
    pub provider_idx: u8,
    pub outcome: u8,
    pub cache_hit: u8,
    pub cost: u64,
    pub latency_ms: u32,
    pub reserved: u32,
}

#[event]
pub struct SessionInitialized {
    pub session: Pubkey,
    pub owner: Pubkey,
    pub authority: Pubkey,
    pub budget_total: u64,
    pub channel_count: u8,
}

#[event]
pub struct StepRecorded {
    pub session: Pubkey,
    pub step_idx: u32,
    pub provider_idx: u8,
    pub cost: u64,
    pub spent: u64,
}

#[event]
pub struct Checkpointed {
    pub session: Pubkey,
    pub checkpoint_count: u8,
    pub step_count: u32,
}

#[event]
pub struct SessionClosed {
    pub session: Pubkey,
    pub step_count: u32,
    pub spent: u64,
}

#[event]
pub struct SessionAborted {
    pub session: Pubkey,
    pub step_count: u32,
}

#[error_code]
pub enum LoopRailError {
    #[msg("budget_total must be > 0 and allocations must not exceed it")]
    InvalidBudget,
    #[msg("providers and allocations must have the same length")]
    ChannelConfigMismatch,
    #[msg("session allows at most MAX_CHANNELS providers")]
    ChannelsFull,
    #[msg("signer is not the session authority or owner")]
    Unauthorized,
    #[msg("session is not open")]
    SessionNotOpen,
    #[msg("step_idx must equal step_count (strictly monotonic)")]
    OutOfOrderStep,
    #[msg("provider_idx is out of range")]
    ProviderIndexOutOfRange,
    #[msg("outcome must be 0..=3")]
    InvalidOutcome,
    #[msg("a cache hit must have zero cost")]
    CacheHitMustBeFree,
    #[msg("session budget exceeded")]
    BudgetExceeded,
    #[msg("provider allocation exceeded")]
    ChannelAllocationExceeded,
    #[msg("at most MAX_CHECKPOINTS checkpoints are allowed")]
    TooManyCheckpoints,
    #[msg("session status does not allow this instruction")]
    InvalidStatus,
}
