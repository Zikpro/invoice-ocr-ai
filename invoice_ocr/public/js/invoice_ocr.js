frappe.ui.form.on("Invoice OCR", {

    refresh(frm) {

        frm.clear_custom_buttons();

        // --------------------------------------------------
        // 📸 CAPTURE BUTTON
        // --------------------------------------------------
        frm.add_custom_button("📸 Capture Invoice", async () => {

            if (frm.is_new()) {
                await frm.save();
            }

            let input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.capture = "environment";

            input.onchange = async function (e) {
                await handle_upload(frm, e.target.files[0]);
            };

            input.click();

        }).addClass("btn-primary");


        // --------------------------------------------------
        // ▶ RUN OCR BUTTON (ONLY IF FILE EXISTS)
        // --------------------------------------------------
        if (frm.doc.invoice_file && frm.doc.status !== "Processing") {

            frm.add_custom_button("▶ Run OCR", async () => {

                frappe.show_alert({
                    message: "Processing invoice...",
                    indicator: "blue"
                });

                await frappe.call({
                    method: "invoice_ocr.api.enqueue_ocr",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: "Reading invoice with AI..."
                });

                frm.reload_doc();

            }).addClass("btn-success");
        }


        // --------------------------------------------------
        // ⏳ PROCESSING STATE
        // --------------------------------------------------
        if (frm.doc.status === "Processing") {

            frm.dashboard.set_headline("⏳ Processing in background...");

            start_polling(frm);
        }


        // --------------------------------------------------
        // 🧾 CREATE PURCHASE INVOICE
        // --------------------------------------------------
        if (frm.doc.status === "Ready" && !frm.doc.purchase_invoice) {

            frm.add_custom_button("🧾 Create Purchase Invoice", async () => {

                await frappe.call({
                    method: "invoice_ocr.api.create_purchase_invoice",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: "Creating Purchase Invoice..."
                });

                frm.reload_doc();

            }).addClass("btn-primary");
        }

    }
});


// =================================================
// FILE UPLOAD HANDLER
// =================================================
async function handle_upload(frm, file) {

    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("doctype", "Invoice OCR");
    formData.append("docname", frm.doc.name);
    formData.append("is_private", 1);

    const response = await fetch("/api/method/upload_file", {
        method: "POST",
        body: formData,
        headers: {
            "X-Frappe-CSRF-Token": frappe.csrf_token
        }
    });

    const result = await response.json();

    if (result.message && result.message.file_url) {

        await frm.set_value("invoice_file", result.message.file_url);

        // 🔥 IMPORTANT: SAVE DOCUMENT AFTER UPLOAD
        await frm.save();

        frappe.show_alert({
            message: "Invoice uploaded. Click Run OCR.",
            indicator: "green"
        });

        frm.reload_doc();
    }
}


// =================================================
// SAFE POLLING
// =================================================
function start_polling(frm) {

    if (frm.__polling) return;
    frm.__polling = true;

    const interval = setInterval(async () => {

        const r = await frappe.db.get_value(
            "Invoice OCR",
            frm.doc.name,
            "status"
        );

        if (!r.message) return;

        if (r.message.status !== "Processing") {
            clearInterval(interval);
            frm.__polling = false;
            frm.reload_doc();
        }

    }, 3000);
}