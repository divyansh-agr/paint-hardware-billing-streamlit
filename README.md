# Paint & Hardware Billing — Streamlit

A billing-only GST invoice web app. It intentionally does **not** include e-invoice QR, IRN, acknowledgement fields, inventory, or accounting.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Default login: `admin` / `admin123`

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository and upload `app.py` and `requirements.txt`.
2. Open Streamlit Community Cloud and create a new app from the repository.
3. Main file: `app.py`.
4. Deploy.

### Important production note
This starter uses SQLite (`billing.db`). Streamlit Community Cloud's local filesystem is not a reliable permanent database across redeploys/restarts. For real shop use, replace SQLite with a hosted database such as Supabase/Postgres or another persistent database before relying on it for business records.

## Invoice

The generated PDF follows the user's supplied layout as a simplified tax invoice: seller details, invoice details, buyer details, item table, taxable value, CGST, SGST, total, amount in words, declaration, and authorized signature. E-invoice QR/IRN/acknowledgement fields are omitted.
