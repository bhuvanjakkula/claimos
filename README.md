# ClaimOS &bull; Cold-Chain Freight Claim Recovery Engine

> **“Give us refrigerated shipments where you lost or abandoned a claim. We'll show whether your existing data contains evidence that can recover the money.”**

ClaimOS is an autonomous web application for refrigerated freight claim recovery. It ingests cold-chain data that shippers already export (logger CSVs, BOLs, and custody timestamps), reconstructs thermal excursions, exposes carrier defenses like the **Dock-Clean Trap**, flags evidence gaps, applies deterministic preliminary attribution, and generates a defensible claim pack with a Carmack reservation notice.

---

## Live Deployment Guides

### 1. Deploy on Render
This repository includes native [render.yaml](render.yaml), [Dockerfile](Dockerfile), and [Procfile](Procfile) configurations:

1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com/), click **New +** &rarr; **Blueprint** (or **Web Service**).
3. Connect your GitHub repository (`claimos`).
4. Render automatically detects `render.yaml` with the following configuration:
   - **Environment**: `Python 3.11.9`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Click **Apply / Deploy**.

---

### 2. Deploy on Vercel
This repository includes native [vercel.json](vercel.json) and [api/index.py](api/index.py) serverless configuration:

1. Push your repository to GitHub.
2. In the [Vercel Dashboard](https://vercel.com/new), select **Add New Project** &rarr; Import your GitHub repo.
3. Keep the default settings (Vercel automatically detects `vercel.json` and `@vercel/python`).
4. Click **Deploy**.
   - Note: In Vercel serverless mode, ClaimOS uses `/tmp/claimos.db` for ephemeral caching and supports PostgreSQL via the `DATABASE_URL` environment variable.

---

### 3. Git Deployment & Remote Commands
Initialize and sync your local repository to GitHub:

```bash
# Add all files to git tracking
git add .

# Create initial release commit
git commit -m "feat: complete ClaimOS engine with Stripe payment links, Render & Vercel deployment configs"

# Add your GitHub remote repository
git remote add origin https://github.com/bhuvanjakkula/claimos.git

# Push to main
git branch -M main
git push -u origin main
```

---

## Membership & Stripe Payment Plans

ClaimOS features transparent USA Dollar monthly subscription plans:

| Tier | Price | Features | Stripe Payment Link |
| :--- | :--- | :--- | :--- |
| **Starter Cargo** | **$49 USD / mo** | 15 shipment excursion analyses/mo, 2-col & 5-col logger CSV, Dock-Clean Trap detector | [Pay $49/mo via Stripe](https://buy.stripe.com/test_fZu28j6mTeOVfbP7CfcjS04) |
| **Customer Pro Membership** | **$199 USD / mo** | Unlimited CSV/BOL ingestion, Full Dock-Clean Counter Strategy, 48-Hour Reefer Demand Dossier, Dormant Audit | [Pay $199/mo via Stripe](https://buy.stripe.com/test_14AdR1fXtgX37Jn7CfcjS05) |
| **Enterprise Carrier Fleet** | **$499 USD / mo** | Multi-user seats, TMS/Reefer Telematics API hooks, Carmack Counsel review, 1-Hour SLA hotline | [Pay $499/mo via Stripe](https://buy.stripe.com/test_cNi14feTp8qxd3H1dRcjS06) |

---

## Local Development & Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run full test suite (18 tests)
python -m pytest -v

# Launch local server on port 8000
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Local endpoints:
- **Sign In & Technology Innovations**: [http://127.0.0.1:8000/?mode=signin](http://127.0.0.1:8000/?mode=signin)
- **Membership & Payments**: [http://127.0.0.1:8000/membership](http://127.0.0.1:8000/membership)
- **Engine Dashboard Console**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)
- **Customer Support Desk**: [http://127.0.0.1:8000/support](http://127.0.0.1:8000/support)
