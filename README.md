# NetSuite Vendor Invoice Downloader

A Python command-line tool that connects to NetSuite via its REST API, searches vendor bill (AP invoice) records, and downloads them as PDF files.

---

## How it works

1. Authenticates with NetSuite using **OAuth 1.0 Token-Based Authentication (TBA)**.
2. Queries vendor bill records using the **SuiteQL API** (SQL-like queries against NetSuite data).
3. Downloads each matched vendor bill as a **PDF** via the NetSuite application print endpoint.
4. Saves the PDFs to a local directory with descriptive filenames.

---

## Requirements

- Python 3.10+
- A NetSuite account with:
  - A **Connected App** (Integration record) that provides a Consumer Key and Consumer Secret.
  - An **Access Token** (Token ID + Token Secret) created for the Integration.
  - The token's role must have permission to: *Transactions > Vendor Bills* (View) and *Reports > SuiteAnalytics Workbook* (View).

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd <repo-dir>
pip install -r requirements.txt
```

### 2. Configure credentials

Copy the example env file and fill in your NetSuite credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
NS_ACCOUNT_ID=1234567          # Your NetSuite account ID
NS_CONSUMER_KEY=...            # From your Integration record
NS_CONSUMER_SECRET=...         # From your Integration record
NS_TOKEN_ID=...                # From your Access Token record
NS_TOKEN_SECRET=...            # From your Access Token record
NS_OUTPUT_DIR=invoices         # Where PDFs will be saved (optional)
```

### 3. Generating NetSuite TBA credentials

1. **Create an Integration** in NetSuite:  
   *Setup → Integration → Manage Integrations → New*  
   Enable *Token-Based Authentication*, save, and copy the Consumer Key and Consumer Secret.

2. **Create an Access Token**:  
   *Setup → Users/Roles → Access Tokens → New*  
   Select your Integration and a Role with appropriate permissions.  
   Copy the Token ID and Token Secret (shown only once).

---

## Usage

### Download all vendor bill PDFs

```bash
python main.py download
```

### Filter by vendor name (substring match)

```bash
python main.py download --vendor-name "Acme"
```

### Filter by vendor internal ID

```bash
python main.py download --vendor-id 12345
```

### Filter by date range

```bash
python main.py download --start-date 2024-01-01 --end-date 2024-12-31
```

### Filter by bill status

```bash
python main.py download --status open
# status options: open, paid, pendingApproval, rejected
```

### Change the output directory

```bash
python main.py download --output-dir /path/to/my/invoices
```

### Combine filters

```bash
python main.py download \
  --vendor-name "Acme" \
  --start-date 2024-06-01 \
  --status open
```

### List vendors (without downloading)

```bash
python main.py list-vendors --limit 100
```

### List vendor bills (without downloading)

```bash
python main.py list-bills --vendor-name "Acme" --limit 25
```

---

## Output

PDFs are saved with descriptive names in the format:

```
{vendor_name}_{transaction_id}_{date}.pdf
```

Example:
```
invoices/
├── Acme_Corp_BILL-00123_2024-03-15.pdf
├── Acme_Corp_BILL-00124_2024-04-01.pdf
└── Globex_Inc_BILL-00200_2024-05-10.pdf
```

Re-running the tool with `--skip-existing` (default) will not re-download files already present on disk.

---

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Project structure

```
.
├── main.py              # CLI entry point
├── requirements.txt
├── .env.example         # Credential template
├── src/
│   ├── auth.py          # OAuth 1.0 TBA setup
│   ├── client.py        # NetSuite REST API client
│   └── downloader.py    # Invoice search & PDF download logic
└── tests/
    ├── test_auth.py
    ├── test_client.py
    └── test_downloader.py
```

---

## Troubleshooting

| Error | Likely cause |
|-------|-------------|
| `Missing required NetSuite credentials` | `.env` file not found or credentials not set |
| HTTP 401 Unauthorized | Incorrect credentials or token expired — regenerate the access token |
| HTTP 403 Forbidden | The token's role lacks permission to view vendor bills |
| HTTP 404 on PDF download | The vendor bill ID doesn't exist or is in a restricted subsidiary |
| Empty results from `list-bills` | No vendor bills match your filters, or the role lacks SuiteQL access |
