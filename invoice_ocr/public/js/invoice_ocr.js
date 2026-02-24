frappe.ui.form.on("Invoice OCR", {

    refresh(frm) {

        // Remove Save button completely
        frm.disable_save();
        frm.page.clear_primary_action();

        // ==================================================
        // 📸 CAMERA BUTTON
        // ==================================================

        frm.add_custom_button("📸 Capture Invoice", async () => {

            if (frm.is_new()) {
                await frm.save();
            }

            let input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.capture = "environment";

            input.onchange = function (e) {
                handle_upload(frm, e.target.files[0]);
            };

            input.click();

        }).addClass("btn-primary");


        // ==================================================
        // 🧾 PURCHASE INVOICE BUTTON (ONLY WHEN READY)
        // ==================================================

        if (frm.doc.status === "Ready" && !frm.doc.purchase_invoice) {

            frm.add_custom_button("🧾 Create Purchase Invoice", async () => {

                await frm.call({
                    method: "invoice_ocr.api.create_purchase_invoice",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Creating Purchase Invoice...")
                });

                frm.reload_doc();

            }).addClass("btn-success");
        }

    },


    // ==================================================
    // 🔥 AUTO SAVE + AUTO OCR WHEN FILE ATTACHED
    // ==================================================

    async invoice_file(frm) {

        if (!frm.doc.invoice_file) return;

        // Auto Save
        await frm.save();

        // Auto Run OCR
        await frm.call({
            method: "invoice_ocr.api.run_ocr",
            args: { docname: frm.doc.name },
            freeze: true,
            freeze_message: __("Processing Invoice Automatically...")
        });

        frm.reload_doc();
    }

});


// ==================================================
// CAMERA UPLOAD FUNCTION
// ==================================================

async function handle_upload(frm, file) {

    if (!file) return;

    let reader = new FileReader();

    reader.onload = async function () {

        try {

            let base64 = reader.result;

            let response = await frappe.call({
                method: "invoice_ocr.api.upload_camera_image",
                args: {
                    docname: frm.doc.name,
                    filedata: base64,
                    filename: file.name
                },
                freeze: true,
                freeze_message: __("Uploading image...")
            });

            if (response.message) {
                frm.set_value("invoice_file", response.message);
            }

        } catch (err) {

            frappe.msgprint({
                title: "Upload Failed",
                message: err.message || err,
                indicator: "red"
            });
        }
    };

    reader.readAsDataURL(file);
}