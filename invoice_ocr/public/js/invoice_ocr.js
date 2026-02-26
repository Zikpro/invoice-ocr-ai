frappe.ui.form.on("Invoice OCR", {

    refresh(frm) {

        // Disable manual save
        frm.disable_save();
        frm.page.clear_primary_action();

        // ============================================
        // 📸 CAMERA BUTTON
        // ============================================

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


        // ============================================
        // ⏳ SAFE AUTO POLLING (NO RACE CONDITION)
        // ============================================

        if (frm.doc.status === "Processing") {

            frm.dashboard.set_headline(
                "⏳ Invoice is processing in background..."
            );

            start_safe_polling(frm);
        }


        // ============================================
        // 🧾 CREATE PURCHASE INVOICE BUTTON
        // ============================================

        if (frm.doc.status === "Ready" && !frm.doc.purchase_invoice) {

            frm.add_custom_button("🧾 Create Purchase Invoice", async () => {

                await frappe.call({
                    method: "invoice_ocr.api.create_purchase_invoice",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Creating Purchase Invoice...")
                });

                frm.reload_doc();

            }).addClass("btn-success");
        }
    },


    // ============================================
    // 🔥 AUTO QUEUE OCR WHEN FILE SET
    // ============================================

    async invoice_file(frm) {

        if (!frm.doc.invoice_file) return;

        // Save ONLY if new document
        if (frm.is_new()) {
            await frm.save();
        }

        frappe.show_alert({
            message: "Invoice queued for background processing...",
            indicator: "blue"
        });

        await frappe.call({
            method: "invoice_ocr.api.enqueue_ocr",
            args: { docname: frm.doc.name }
        });

        // DO NOT reload immediately (prevents version conflict)
        setTimeout(() => {
            frm.reload_doc();
        }, 3000);
    }
});


// =================================================
// 🔁 SAFE POLLING FUNCTION (NO SAVE, NO CONFLICT)
// =================================================

function start_safe_polling(frm) {

    if (frm.__polling) return;
    frm.__polling = true;

    let interval = setInterval(async () => {

        let r = await frappe.db.get_value(
            "Invoice OCR",
            frm.doc.name,
            "status"
        );

        if (r.message.status !== "Processing") {
            clearInterval(interval);
            frm.__polling = false;
            frm.reload_doc();
        }

    }, 4000);
}


// =================================================
// 🚀 SAFE FILE UPLOAD
// =================================================

async function handle_upload(frm, file) {

    if (!file) return;

    const compressed = await compressImage(file, 1200, 0.7);

    let formData = new FormData();
    formData.append("file", compressed);
    formData.append("doctype", "Invoice OCR");
    formData.append("docname", frm.doc.name);
    formData.append("is_private", 1);

    let response = await fetch("/api/method/upload_file", {
        method: "POST",
        body: formData,
        headers: {
            "X-Frappe-CSRF-Token": frappe.csrf_token
        }
    });

    let result = await response.json();

    if (result.message && result.message.file_url) {
        frm.set_value("invoice_file", result.message.file_url);
    }
}


// =================================================
// 🧠 IMAGE COMPRESSION
// =================================================

function compressImage(file, maxWidth, quality) {

    return new Promise((resolve) => {

        const img = new Image();
        const reader = new FileReader();

        reader.onload = function (e) {
            img.src = e.target.result;
        };

        img.onload = function () {

            const scale = Math.min(1, maxWidth / img.width);

            const canvas = document.createElement("canvas");
            canvas.width = img.width * scale;
            canvas.height = img.height * scale;

            const ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

            canvas.toBlob(
                (blob) => {
                    resolve(new File([blob], file.name, { type: "image/jpeg" }));
                },
                "image/jpeg",
                quality
            );
        };

        reader.readAsDataURL(file);
    });
}