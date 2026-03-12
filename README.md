# Zikpro Invoice OCR

AI-powered Invoice OCR Agent for ERPNext powered by DeepInfra.

Invoice OCR automatically extracts structured invoice data from images and PDFs using advanced AI models, validates financial totals, matches suppliers intelligently, and creates Purchase Invoices inside ERPNext.

---

## 🧭 How It Works

1. User uploads invoice (Image or PDF)
2. AI extracts structured data using DeepInfra models
3. System validates totals and tax calculations
4. Supplier is matched automatically
5. User reviews extracted data
6. Purchase Invoice is generated inside ERPNext

Processing runs in background using Frappe background jobs for better performance.

---

## 🚀 Features

### 📸 Smart Invoice Capture
- Upload PNG, JPG, JPEG, or PDF invoices
- Mobile camera support
- Secure private file storage

### 🧠 AI-Powered OCR
- Vision model for image invoices
- Text model for structured extraction
- Layout-aware parsing
- Context-aware extraction

### 🤖 Intelligent Data Extraction
- Invoice Number
- Invoice Date
- Supplier Name
- Line Items (Qty, Rate, Amount)
- VAT / Tax detection
- Currency detection

### 🔎 Supplier Matching Engine
- Intelligent fuzzy matching
- ERP Supplier auto-mapping
- Manual fallback supported

### 💰 Financial Validation Engine
- Net total calculation
- Tax validation
- Grand total reconciliation
- Risk scoring (LOW / MEDIUM / HIGH)
- Mismatch detection

### 📊 Semantic JSON Output
- Normalized structured AI output
- Stored for audit and debugging

### 🧾 Auto Purchase Invoice Creation
- One-click Purchase Invoice generation
- Expense account auto-detection
- Tax account auto-mapping
- Duplicate protection

### ⚙ Background Processing
- Uses Frappe background jobs
- Non-blocking UI
- Live processing status polling

---

## 🏗 Architecture Overview

Invoice OCR uses a modular AI pipeline:

1. Vision OCR Agent  
2. Layout Detection Agent  
3. Context Builder  
4. Header Extraction Agent  
5. Line Item Extraction Agent  
6. Tax Detection Agent  
7. Financial Validator  
8. Supplier Intelligence Engine  

All AI processing is powered by DeepInfra models.

---

## 🔐 Configuration (Required)

Before using the app:

1. Install the app  
2. Open **DeepInfra Settings**  
3. Enter your DeepInfra API Key  
4. Save  

The API key is securely stored in a Password field and never hardcoded.

---


## Requirements

- ERPNext v15 or later
- Frappe Framework v15
- DeepInfra API Key

---

## 📦 Installation

Using Bench CLI:

```bash
bench get-app https://github.com/Zikpro/invoice-ocr-ai
bench --site your-site-name install-app zikpro_invoice_ocr
bench migrate
```





## 📸 Screenshots & Workflow
---


### 🔐 DeepInfra API Configuration

Before running OCR, configure your DeepInfra API key  
inside the DeepInfra Settings DocType.

![DeepInfra Settings](screenshots/10-deepinfra-settings.png)

---

### 1️⃣ Upload Invoice

Users can upload invoice files in PNG, JPG, JPEG, or PDF format.  
Mobile camera capture is also supported for real-time invoice scanning.

![Upload Invoice](screenshots/01-upload-invoice.png)

---

### 2️⃣ Draft Before OCR

After upload, the document is saved in Draft state.  
Users can review or modify before triggering OCR processing.

![Draft State](screenshots/02-draft-before-ocr.png)

---

### 3️⃣ Background Processing

OCR runs asynchronously using Frappe background jobs.  
The system shows processing status without blocking the UI.

![Processing](screenshots/03-processing-state.png)

---

### 4️⃣ Header Extraction

AI extracts structured header information including:

- Supplier Name  
- Invoice Date  
- Invoice Number  
- Currency  

![Header Extraction](screenshots/04-header-extraction.png)

---

### 5️⃣ Items & Taxes Extraction

Line items and tax rows are automatically detected and structured:

- Item Name  
- Quantity  
- Rate  
- Amount  
- Tax Accounts  

![Items & Taxes](screenshots/05-items-and-taxes.png)

---

### 6️⃣ Raw OCR Output

Full OCR raw output is stored for audit and debugging purposes.

![Raw OCR](screenshots/06-raw-ocr-output.png)

---

### 7️⃣ Semantic JSON Output

AI generates structured semantic JSON including:

- Confidence score  
- Risk level  
- Financial validation  
- Context detection  

![Semantic JSON](screenshots/07-semantic-json.png)

---

### 8️⃣ Duplicate Protection

The system prevents duplicate Purchase Invoice creation  
by checking existing invoice numbers.

![Duplicate Protection](screenshots/08-duplicate-protection.png)

---

### 9️⃣ Purchase Invoice Created

With one click, a validated Purchase Invoice is generated  
inside ERPNext Accounting.

![Purchase Invoice](screenshots/09-purchase-invoice-created.png)

---

### 🔟 Mobile Processing

Invoice OCR works seamlessly on mobile devices.

![Mobile Processing](screenshots/11-mobile-processing.jpeg)

---

### 1️⃣1️⃣ Mobile Menu Access

Users can trigger OCR actions directly from the mobile menu.

![Mobile Menu](screenshots/12-mobile-menu.jpeg)
---


## 🧠 AI Stack

- DeepInfra Vision Models
- Layout-aware OCR processing
- AI agents pipeline
- Financial validation engine
- Supplier matching intelligence

---

## 🔒 Security

- No API keys stored in source code
- API key stored securely using Frappe Password field
- Private file storage
- Background job isolation
- Error logging for audit purposes

---

## 📄 License

MIT

