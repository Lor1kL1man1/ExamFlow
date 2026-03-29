# ExamFlow Deployment Guide (Render + Vercel)

This guide deploys:
- Backend (Flask) on **Render**
- Frontend (Vite/React) on **Vercel**
- Database on **Render PostgreSQL**

---

## 1) Deploy Backend on Render

### A. Create PostgreSQL
1. In Render dashboard, create a **PostgreSQL** service.
2. Copy the **External Database URL**.

### B. Create Web Service (Backend)
1. Create a new **Web Service** from this repo.
2. Set **Root Directory** to `backend`.
3. Build Command:
   `pip install -r app/requirements.txt`
4. Start Command:
   `gunicorn run:app --bind 0.0.0.0:$PORT`

### C. Environment Variables (Backend)
Set these in Render:
- `SECRET_KEY` = a strong random string
- `DATABASE_URL` = your Render PostgreSQL URL

> Note: The app currently auto-seeds defaults when DB is empty.

### D. Verify Backend
After deploy, open:
- `https://<your-backend>.onrender.com/api/health`

You should get:
```json
{"status":"ok"}
```

---

## 2) Deploy Frontend on Vercel

1. Import this repo in Vercel.
2. Set **Root Directory** to `frontend`.
3. Build Command:
   `npm run build`
4. Output Directory:
   `dist`

### Environment Variable (Frontend)
Set in Vercel project settings:
- `VITE_API_URL` = `https://<your-backend>.onrender.com/api`

Redeploy after setting env vars.

---

## 3) Final Checks

1. Open frontend URL.
2. Test these flows:
   - Load dashboard/pages
   - Generate schedule
   - Save session changes
   - Export endpoints
3. If requests fail, verify `VITE_API_URL` has no trailing slash beyond `/api`.

---

## Optional: Single-domain setup later
If you want one domain (no cross-origin), place frontend and backend behind one reverse proxy (e.g., Nginx) and keep frontend API as `/api`.
