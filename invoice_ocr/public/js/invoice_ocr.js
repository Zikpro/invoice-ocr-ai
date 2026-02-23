frappe.ui.form.on("Invoice OCR", {

    refresh(frm) {

        frm.clear_custom_buttons();
        frm.page.clear_primary_action();

        // ==================================================
        // 📸 OPEN CAMERA BUTTON
        // ==================================================

        frm.add_custom_button("📸 Open Camera", () => {

            let input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.capture = "environment";

            input.onchange = function(e) {

                let file = e.target.files[0];
                if (!file) return;

                let reader = new FileReader();

                reader.onload = async function() {

                    try {

                        // ✅ remove metadata header
                        let base64 = reader.result.split(",")[1];

                        let r = await frappe.call({
                            method: "frappe.client.attach_file",
                            args: {
                                doctype: frm.doctype,
                                docname: frm.doc.name,
                                filename: file.name,
                                filedata: base64,
                                is_private: 1
                            },
                            freeze: true,
                            freeze_message: __("Uploading image...")
                        });

                        frm.set_value("camera_capture", r.message.file_url);

                        await frm.save();

                        frappe.show_alert({
                            message: "Image Uploaded Successfully",
                            indicator: "green"
                        });

                        frm.reload_doc();

                    } catch (err) {
                        frappe.msgprint({
                            title: "Upload Error",
                            message: err.message || err,
                            indicator: "red"
                        });
                    }
                };

                reader.readAsDataURL(file);
            };

            input.click();

        }).addClass("btn-primary");


        // ==================================================
        // ▶ RUN OCR
        // ==================================================

        if ((frm.doc.invoice_file || frm.doc.camera_capture) && frm.doc.status === "Draft") {

            frm.add_custom_button("▶ Run OCR", () => {

                frm.call({
                    method: "invoice_ocr.api.run_ocr",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Running OCR...")
                }).then(() => {
                    frm.reload_doc();
                });

            }).addClass("btn-primary");
        }


        // ==================================================
        // 🧾 GENERATE PURCHASE INVOICE
        // ==================================================

        if (frm.doc.status === "Ready" && !frm.doc.purchase_invoice) {

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
                        message: "Purchase Invoice Created",
                        indicator: "green"
                    });

                    frm.reload_doc();

                } catch (err) {
                    frappe.msgprint({
                        title: "Purchase Invoice Error",
                        message: err.message || err,
                        indicator: "red"
                    });
                }

            }).addClass("btn-success");
        }


        // ==================================================
        // 📄 VIEW PURCHASE INVOICE
        // ==================================================

        if (frm.doc.purchase_invoice) {

            frm.add_custom_button("📄 View Purchase Invoice", () => {
                frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice);
            });
        }

    }
});