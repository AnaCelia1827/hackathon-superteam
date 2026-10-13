# Person B dashboard

A local B7 prototype powered by the deterministic B3 scenario. This is a static page with no dependencies while A6/A7 and the SSE transport are unavailable. The implementation plan calls for Next.js in the final version.

```powershell
cd apps/runtime
python -m looprail.demo --output ../dashboard/data/mock-50.json
cd ../dashboard
python -m http.server 8000
```

Open `http://localhost:8000`. The dashboard labels the data as simulated, shows no fictitious settlement, and keeps the kill switch disabled until a live session and abort endpoint exist. The step timeline shows 10 entries per page.

Use the header button to switch between light and dark mode. The browser remembers the selected theme.
