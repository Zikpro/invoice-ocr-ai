frappe.ui.form.on("Invoice OCR", {

    refresh(frm) {

        // --------------------------------------------------
        // CLEAN UI
        // --------------------------------------------------
        frm.clear_custom_buttons();
        frm.page.clear_primary_action();

        // --------------------------------------------------
        // OCR CONFIDENCE INDICATOR
        // --------------------------------------------------
        if (frm.doc.confidence !== undefined && frm.doc.confidence !== null) {

            let color =
                frm.doc.confidence >= 70 ? "green" :
                frm.doc.confidence >= 40 ? "orange" : "orange";

            frm.dashboard.set_headline(
                `<span class="indicator ${color}">
                    OCR Confidence: ${frm.doc.confidence}%
                 </span>`
            );
        }

        // --------------------------------------------------
        // 📸 DIRECT CAMERA BUTTON (PRO VERSION)
        // --------------------------------------------------
        frm.add_custom_button("📸 Open Camera", () => {

            let input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.capture = "environment";

            input.onchange = function(e) {

                let file = e.target.files[0];
                if (!file) return;

                let reader = new FileReader();

                reader.onload = function() {

                    frappe.call({
                        method: "frappe.client.attach_file",
                        args: {
                            doctype: frm.doctype,
                            docname: frm.doc.name,
                            filename: file.name,
                            filedata: reader.result,
                            is_private: 1
                        },
                        callback: function(r) {

                            if (r.message && r.message.file_url) {

                                // SET FILE FIELD
                                frm.set_value("invoice_file", r.message.file_url);

                                frm.save().then(() => {

                                    frappe.show_alert({
                                        message: "Image Captured & Linked",
                                        indicator: "green"
                                    });

                                    frm.reload_doc();
                                });
                            }
                        }
                    });

                };

                reader.readAsDataURL(file);
            };

            input.click();

        }).addClass("btn-primary");


        // --------------------------------------------------
        // RUN OCR
        // --------------------------------------------------
        if (frm.doc.invoice_file && frm.doc.status === "Draft") {

            frm.add_custom_button("▶ Run OCR", () => {

                frm.call({
                    method: "invoice_ocr.api.run_ocr",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Running OCR...")
                })
                .then(() => {
                    frm.reload_doc();
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
                });

            });

        }


        // --------------------------------------------------
        // GENERATE PURCHASE INVOICE (AUTO SAVE FIRST)
        // --------------------------------------------------
        if (
            frm.doc.status === "Ready" &&
            Array.isArray(frm.doc.items) &&
            frm.doc.items.length > 0 &&
            !frm.doc.purchase_invoice
        ) {

            frm.add_custom_button("🧾 Generate Purchase Invoice", async () => {

                try {

                    if (frm.is_dirty()) {
                        await frm.save();
                    }

                    await frm.call({
                        method: "invoice_ocr.api.create_purchase_invoice",
                        args: { docname: frm.doc.name },
                        freeze: true,
                        freeze_message: __("Creating Purchase Invoice...")
                    });

                    frappe.show_alert({
                        message: __("Purchase Invoice Created"),
                        indicator: "green"
                    });

                    frm.reload_doc();

                } catch (err) {

                    frappe.msgprint({
                        title: __("Purchase Invoice Error"),
                        message: err.message || err,
                        indicator: "red"
                    });

                }

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
    },


    // --------------------------------------------------
    // AUTO SAVE ON FIELD CHANGE
    // --------------------------------------------------

    supplier(frm) { auto_save(frm); },
    invoice_date(frm) { auto_save(frm); },
    currency(frm) { auto_save(frm); },
    invoice_number(frm) { auto_save(frm); }

});


// --------------------------------------------------
// GLOBAL AUTO SAVE FUNCTION
// --------------------------------------------------

function auto_save(frm) {
    if (frm.is_dirty()) {
        frm.save().catch((err) => {
            console.error("Auto save failed", err);
        });
    }
}