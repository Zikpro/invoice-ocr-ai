// Copyright (c) 2026, Zikpro Ltd
// For license information, please see license.txt

frappe.ui.form.on("DeepInfra Settings", {

    refresh: function(frm) {

        frm.add_custom_button("Test Connection", function() {

            frappe.call({
                method: "invoice_ocr.api.test_deepinfra_connection",
                freeze: true,
                freeze_message: "Testing DeepInfra connection...",
                callback: function(r) {

                    if (!r.exc) {
                        frappe.msgprint({
                            title: "Success",
                            message: "DeepInfra connection successful ✅",
                            indicator: "green"
                        });
                    }

                }
            });

        });

    }

});