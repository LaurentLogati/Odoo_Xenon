# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) 2013-2015 Akretion (http://www.akretion.com)

import base64
import csv
import io

from odoo import fields, models, _
from odoo.exceptions import AccessDenied, UserError
from odoo.tools import float_is_zero


class L10nFrFecExportWizardXenon(models.TransientModel):
    _inherit = 'l10n_fr.fec.export.wizard'

    def _do_query_unaffected_earnings_cabinet(self):
        """
        Calcule la somme des soldes de clôture pour tous les comptes de type
        qui ne reportent pas le solde en début d'exercice (charges/produits).
        """
        sql_query = '''
        SELECT
            'OUV' AS JournalCode,
            %s AS EcritureDate,
            '120/129' AS CompteNum,
            'Benefice (perte) reporte(e)' AS CompteLib,
            replace(CASE WHEN COALESCE(sum(aml.balance), 0) <= 0 THEN '0,00' ELSE to_char(SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Debit,
            replace(CASE WHEN COALESCE(sum(aml.balance), 0) >= 0 THEN '0,00' ELSE to_char(-SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Credit,
            '-' AS PieceRef,
            '' AS EcritureLet
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
        WHERE
            am.date < %s
            AND am.company_id = %s
            AND aa.account_type NOT IN (
                'asset_receivable', 'liability_payable',
                'asset_cash', 'liability_credit_card',
                'asset_current', 'liability_current',
                'asset_non_current', 'liability_non_current',
                'equity', 'equity_unaffected'
            )
            AND (aml.debit != 0 OR aml.credit != 0)
        '''
        if self.export_type == "official":
            sql_query += " AND am.state = 'posted'"

        company = self.env.company
        formatted_date_from = fields.Date.to_string(self.date_from).replace('-', '')
        self._cr.execute(sql_query, (formatted_date_from, self.date_from, company.id))
        row = self._cr.fetchone()
        return list(row) if row else []

    def _get_company_legal_data_cabinet(self, company):
        """Retourne le SIREN ou le numéro de TVA selon le contexte."""
        dom_tom_group = self.env.ref('l10n_fr.dom-tom')
        is_dom_tom = company.account_fiscal_country_id.code in dom_tom_group.country_ids.mapped('code')
        if not company.vat or is_dom_tom:
            return ''
        elif company.country_id.code == 'FR' and len(company.vat) >= 13:
            return company.vat[4:13]
        else:
            return company.vat

    def generate_fec_cabinet(self):
        self.ensure_one()
        if not (self.env.is_admin() or self.env.user.has_group('account.group_account_user')):
            raise AccessDenied()

        today = fields.Date.today()
        if self.date_from > today or self.date_to > today:
            raise UserError(_('Vous ne pouvez pas définir une date dans le futur.'))
        if self.date_from >= self.date_to:
            raise UserError(_('La date de début doit être antérieure à la date de fin.'))

        company = self.env.company
        currency_digits = 2
        formatted_date_from = fields.Date.to_string(self.date_from).replace('-', '')
        formatted_date_to = fields.Date.to_string(self.date_to).replace('-', '')

        header = [
            'JournalCode',   # 0
            'EcritureDate',  # 1
            'CompteNum',     # 2
            'EcritureLib',   # 3
            'Debit',         # 4
            'Credit',        # 5
            'PieceRef',      # 6
            'EcritureLet',   # 7
        ]
        rows_to_write = [header]

        # SOLDES INITIAUX - résultat exercice précédent
        unaffected_earnings_xml_ref = self.env.ref('account.data_unaffected_earnings', raise_if_not_found=False)
        unaffected_earnings_line = True
        unaffected_earnings_results = []
        if unaffected_earnings_xml_ref:
            unaffected_earnings_results = self._do_query_unaffected_earnings_cabinet()
            unaffected_earnings_line = False

        # SOLDES INITIAUX - comptes hors tiers
        sql_query = '''
        SELECT
            'OUV' AS JournalCode,
            %s AS EcritureDate,
            MIN(aa.code) AS CompteNum,
            replace(replace(MIN(aa.name), '|', ''), E'\\t', '') AS EcritureLib,
            replace(CASE WHEN sum(aml.balance) <= 0 THEN '0,00' ELSE to_char(SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Debit,
            replace(CASE WHEN sum(aml.balance) >= 0 THEN '0,00' ELSE to_char(-SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Credit,
            '-' AS PieceRef,
            '' AS EcritureLet,
            MIN(aa.id) AS CompteID
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
        WHERE
            am.date < %s
            AND am.company_id = %s
            AND aa.account_type IN (
                'asset_cash', 'liability_credit_card',
                'asset_current', 'liability_current',
                'asset_non_current', 'liability_non_current',
                'equity', 'equity_unaffected'
            )
            AND (aml.debit != 0 OR aml.credit != 0)
        '''
        if self.export_type == "official":
            sql_query += " AND am.state = 'posted'"
        sql_query += '''
        GROUP BY aml.account_id, aa.account_type
        HAVING round(sum(aml.balance), %s) != 0
        AND aa.account_type NOT IN ('asset_receivable', 'liability_payable')
        '''
        self._cr.execute(sql_query, (formatted_date_from, self.date_from, company.id, currency_digits))

        unaffected_earnings_account_type = 'equity_unaffected'
        for row in self._cr.fetchall():
            listrow = list(row)
            account_id = listrow.pop()
            if not unaffected_earnings_line:
                account = self.env['account.account'].browse(account_id)
                if account.account_type == unaffected_earnings_account_type:
                    unaffected_earnings_line = True
                    current_amount = float(listrow[4].replace(',', '.')) - float(listrow[5].replace(',', '.'))
                    unaffected_amount = float(unaffected_earnings_results[4].replace(',', '.')) - float(unaffected_earnings_results[5].replace(',', '.'))
                    total = current_amount + unaffected_amount
                    if float_is_zero(total, precision_digits=currency_digits):
                        continue
                    if total > 0:
                        listrow[4] = str(total).replace('.', ',')
                        listrow[5] = '0,00'
                    else:
                        listrow[4] = '0,00'
                        listrow[5] = str(-total).replace('.', ',')
            rows_to_write.append(listrow)

        # Ajout manuel si le compte de résultat n'était pas dans la sélection
        if (not unaffected_earnings_line
                and unaffected_earnings_results
                and (unaffected_earnings_results[4] != '0,00' or unaffected_earnings_results[5] != '0,00')):
            unaffected_account = self.env['account.account'].search(
                [('account_type', '=', unaffected_earnings_account_type), ('company_id', '=', company.id)], limit=1)
            if unaffected_account:
                unaffected_earnings_results[2] = unaffected_account.code
            rows_to_write.append(unaffected_earnings_results)

        # SOLDES INITIAUX - comptes tiers (receivable/payable)
        sql_query = '''
        SELECT
            'OUV' AS JournalCode,
            %s AS EcritureDate,
            CASE WHEN rp.id IS NULL THEN MIN(aa.code) ELSE MIN(aa.code) || '_' || rp.id END AS CompteNum,
            CASE WHEN aa.account_type IN ('asset_receivable', 'liability_payable')
            THEN COALESCE(replace(rp.name, '|', '-'), MIN(aa.name))
            ELSE ''
            END AS EcritureLib,
            replace(CASE WHEN sum(aml.balance) <= 0 THEN '0,00' ELSE to_char(SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Debit,
            replace(CASE WHEN sum(aml.balance) >= 0 THEN '0,00' ELSE to_char(-SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Credit,
            '-' AS PieceRef,
            '' AS EcritureLet
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id = aml.move_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            JOIN account_account aa ON aa.id = aml.account_id
        WHERE
            am.date < %s
            AND am.company_id = %s
            AND aa.account_type IN ('asset_receivable', 'liability_payable')
            AND (aml.debit != 0 OR aml.credit != 0)
        '''
        if self.export_type == "official":
            sql_query += " AND am.state = 'posted'"
        sql_query += '''
        GROUP BY aml.account_id, aa.account_type, rp.ref, rp.id
        HAVING round(sum(aml.balance), %s) != 0
        '''
        self._cr.execute(sql_query, (formatted_date_from, self.date_from, company.id, currency_digits))
        for row in self._cr.fetchall():
            rows_to_write.append(list(row))

        # ÉCRITURES DE LA PÉRIODE
        sql_query = '''
        SELECT
            replace(replace(replace(replace(aj.code, '|', '-'), E'\\t', ''), 'FACTU', 'AC'), 'FAC', 'VE') AS JournalCode,
            TO_CHAR(am.date, 'YYYYMMDD') AS EcritureDate,
            CASE WHEN aa.account_type IN ('asset_receivable', 'liability_payable') THEN
                CASE WHEN rp.id IS NULL THEN aa.code ELSE aa.code || '_' || rp.id END
            ELSE aa.code END AS CompteNum,
            COALESCE(
                replace(replace(rp.name, '|', '-'), E'\\t', ''),
                replace(replace(replace(replace(replace(aml.name, '|', '-'), E'\\t', ''), E'\\n', ''), E'\\r', ''), ';', ''),
                aa.name
            ) AS EcritureLib,
            replace(CASE WHEN aml.debit = 0 THEN '0,00' ELSE to_char(aml.debit, '000000000000000D99') END, '.', ',') AS Debit,
            replace(CASE WHEN aml.credit = 0 THEN '0,00' ELSE to_char(aml.credit, '000000000000000D99') END, '.', ',') AS Credit,
            substring(replace(replace(am.name, '|', '-'), E'\\t', ''), position('/' in am.name) + 1, 20) AS PieceRef,
            CASE WHEN rec.name IS NULL THEN '' ELSE rec.name END AS EcritureLet
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id = aml.move_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            JOIN account_journal aj ON aj.id = am.journal_id
            JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN res_currency rc ON rc.id = aml.currency_id
            LEFT JOIN account_full_reconcile rec ON rec.id = aml.full_reconcile_id
        WHERE
            am.date >= %s
            AND am.date <= %s
            AND am.company_id = %s
            AND (aml.debit != 0 OR aml.credit != 0)
            AND aj.code != 'CABA'
        '''
        if self.export_type == "official":
            sql_query += " AND am.state = 'posted'"

        sql_query += '''
        UNION ALL
        SELECT
            replace(replace(replace(replace(aj.code, '|', '-'), E'\\t', ''), 'FACTU', 'AC'), 'FAC', 'VE') AS JournalCode,
            TO_CHAR(am.date, 'YYYYMMDD') AS EcritureDate,
            CASE WHEN aa.account_type IN ('asset_receivable', 'liability_payable') THEN
                CASE WHEN rp.id IS NULL THEN aa.code ELSE aa.code || '_' || rp.id END
            ELSE aa.code END AS CompteNum,
            COALESCE(
                replace(replace(rp.name, '|', '-'), E'\\t', ''),
                replace(replace(replace(replace(replace(aml.name, '|', '-'), E'\\t', ''), E'\\n', ''), E'\\r', ''), ';', ''),
                aa.name
            ) AS EcritureLib,
            replace(CASE WHEN aml.debit = 0 THEN '0,00' ELSE to_char(aml.debit, '000000000000000D99') END, '.', ',') AS Debit,
            replace(CASE WHEN aml.credit = 0 THEN '0,00' ELSE to_char(aml.credit, '000000000000000D99') END, '.', ',') AS Credit,
            substring(replace(replace(am.name, '|', '-'), E'\\t', ''), position('/' in am.name) + 1, 20) AS PieceRef,
            CASE WHEN rec.name IS NULL THEN '' ELSE rec.name END AS EcritureLet
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id = aml.move_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            JOIN account_journal aj ON aj.id = am.journal_id
            JOIN account_account aa ON aa.id = aml.account_id AND substring(aa.code, 1, 3) = '445'
            LEFT JOIN res_currency rc ON rc.id = aml.currency_id
            LEFT JOIN account_full_reconcile rec ON rec.id = aml.full_reconcile_id
        WHERE
            am.date >= %s
            AND am.date <= %s
            AND am.company_id = %s
            AND (aml.debit != 0 OR aml.credit != 0)
            AND am.state = 'posted'
            AND aj.code = 'CABA'
        ORDER BY
            EcritureDate,
            JournalCode,
            PieceRef
        '''
        self._cr.execute(sql_query, (
            self.date_from, self.date_to, company.id,
            self.date_from, self.date_to, company.id,
        ))
        for row in self._cr.fetchall():
            rows_to_write.append(list(row))

        fecvalue = self._csv_write_rows_cabinet(rows_to_write)
        suffix = '-Brouillon compris' if self.export_type == "nonofficial" else ''
        filename = 'ExportCabinet_du%s_au_%s%s.csv' % (formatted_date_from, formatted_date_to, suffix)

        self.write({
            'fec_data': base64.encodebytes(fecvalue),
            'filename': filename,
        })

        return {
            'name': 'Export Cabinet',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=l10n_fr.fec.export.wizard&id=%s&filename_field=filename&field=fec_data&download=true&filename=%s" % (self.id, filename),
            'target': 'self',
        }

    def _csv_write_rows_cabinet(self, rows, lineterminator='\r\n'):
        """Écrit les lignes FEC dans un fichier CSV avec séparateur pipe."""
        fecfile = io.BytesIO()
        # csv natif en v18 (pycompat supprimé)
        text_wrapper = io.TextIOWrapper(fecfile, encoding='utf-8', newline='')
        writer = csv.writer(text_wrapper, delimiter='|', lineterminator='')

        rows_length = len(rows)
        for i, row in enumerate(rows):
            row = [str(col) if col is not None else '' for col in row]
            if i < rows_length - 1:
                row[-1] += lineterminator
            writer.writerow(row)

        text_wrapper.flush()
        fecvalue = fecfile.getvalue()
        fecfile.close()
        return fecvalue
