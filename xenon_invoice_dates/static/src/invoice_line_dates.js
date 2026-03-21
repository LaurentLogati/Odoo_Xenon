/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductLabelSectionAndNoteListRender } from "@account/components/product_label_section_and_note_field/product_label_section_and_note_field";

/**
 * Extension du renderer pour afficher start_date et end_date
 * sur les lignes de facture (module account_invoice_start_end_dates)
 */
patch(ProductLabelSectionAndNoteListRender.prototype, {
    getActiveColumns(list) {
        const activeColumns = super.getActiveColumns(list);
        return activeColumns;
    },

    getCellClass(column, record) {
        // Ne pas masquer start_date et end_date sur les lignes section/note
        if (
            ["start_date", "end_date"].includes(column.name) &&
            this.isSectionOrNote(record)
        ) {
            return super.getCellClass(column, record).replace("o_hidden", "").trim();
        }
        return super.getCellClass(column, record);
    },
});
