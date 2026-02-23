frappe.ui.form.on("Invoice OCR", {

    refresh(frm) {

        frm.clear_custom_buttons();
        frm.page.clear_primary_action();

        // ==================================================
        // 📸 BUTTON 1: DIRECT CAMERA CAPTURE
        // ==================================================

        frm.add_custom_button("📸 Capture Invoice", async () => {

            if (frm.is_new()) {
                await frm.save();
            }

            let input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.capture = "environment";   // Forces camera on mobile

            input.onchange = function (e) {
                handle_upload(frm, e.target.files[0]);
            };

            input.click();

        }).addClass("btn-primary");


        // ==================================================
        // 📂 BUTTON 2: SYSTEM FILE UPLOAD
        // ==================================================

        frm.add_custom_button("📂 Upload Invoice File", async () => {

            if (frm.is_new()) {
                await frm.save();
            }

            let input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*,.pdf";  // allow PDF also

            input.onchange = function (e) {
                handle_upload(frm, e.target.files[0]);
            };

            input.click();

        });


        // ==================================================
        // ▶ RUN OCR
        // ==================================================

        if (frm.doc.invoice_file && frm.doc.status === "Draft") {

            frm.add_custom_button("▶ Run OCR", async () => {

                await frm.call({
                    method: "invoice_ocr.api.run_ocr",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Running OCR...")
                });

                frm.reload_doc();
            }).addClass("btn-primary");
        }

    }
});


// ==================================================
// COMMON UPLOAD FUNCTION
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
                freeze_message: __("Uploading file...")
            });

            if (response.message) {

                frm.set_value("invoice_file", response.message);
                await frm.save();

                frappe.show_alert({
                    message: "Invoice uploaded successfully",
                    indicator: "green"
                });

                frm.reload_doc();
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