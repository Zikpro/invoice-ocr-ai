frappe.ui.form.on("Invoice OCR", {
    refresh(frm) {

        // --------------------------------------------------
        // CLEAN UI (avoid duplicate buttons)
        // --------------------------------------------------
        frm.clear_custom_buttons();
        frm.page.clear_primary_action();

        // --------------------------------------------------
        // OCR CONFIDENCE INDICATOR
        // --------------------------------------------------
        if (frm.doc.confidence !== undefined && frm.doc.confidence !== null) {
            let color =
                frm.doc.confidence >= 70 ? "green" :
                frm.doc.confidence >= 40 ? "orange" : "red";

            frm.dashboard.set_headline(
                `<span class="indicator ${color}">
                    OCR Confidence: ${frm.doc.confidence}%
                 </span>`
            );
        }

        // --------------------------------------------------
        // RUN OCR
        // --------------------------------------------------
        if (frm.doc.invoice_file && frm.doc.status === "Draft") {
            frm.add_custom_button("▶ Run OCR", () => {
                frm.call({
                    method: "invoice_ocr.api.run_ocr",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Running OCR, please wait...")
                })
                .then(() => {
                    frm.reload_doc();
                })
                .catch((err) => {
                    frappe.msgprint({
                        title: __("OCR Error"),
                        message: err.message || err,
                        indicator: "red"
                    });
                });
            }).addClass("btn-primary");
        }

        // --------------------------------------------------
        // RESET OCR
        // --------------------------------------------------
        if (frm.doc.status && frm.doc.status !== "Draft") {
            frm.add_custom_button("🔄 Reset OCR", () => {
                frm.call({
                    method: "invoice_ocr.api.reset_ocr",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Resetting OCR...")
                })
                .then(() => {
                    frm.reload_doc();
                })
                .catch((err) => {
                    frappe.msgprint({
                        title: __("Reset Error"),
                        message: err.message || err,
                        indicator: "red"
                    });
                });
            });
        }

        // --------------------------------------------------
        // GENERATE PURCHASE INVOICE
        // --------------------------------------------------
        if (
            frm.doc.status === "Ready" &&
            Array.isArray(frm.doc.items) &&
            frm.doc.items.length > 0 &&
            !frm.doc.purchase_invoice
        ) {
            frm.add_custom_button("🧾 Generate Purchase Invoice", () => {
                frm.call({
                    method: "invoice_ocr.api.create_purchase_invoice",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Creating Purchase Invoice...")
                })
                .then(() => {
                    frappe.show_alert({
                        message: __("Purchase Invoice Created"),
                        indicator: "green"
                    });
                    frm.reload_doc();
                })
                .catch((err) => {
                    frappe.msgprint({
                        title: __("Purchase Invoice Error"),
                        message: err.message || err,
                        indicator: "red"
                    });
                });
            }).addClass("btn-success");
        }

        // --------------------------------------------------
        // VIEW PURCHASE INVOICE
        // --------------------------------------------------
        if (frm.doc.purchase_invoice) {
            frm.add_custom_button("📄 View Purchase Invoice", () => {
                frappe.set_route(
                    "Form",
                    "Purchase Invoice",
                    frm.doc.purchase_invoice
                );
            });
        }
    }
});