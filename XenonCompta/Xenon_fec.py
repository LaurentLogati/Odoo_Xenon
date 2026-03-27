# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) 2013-2015 Akretion (http://www.akretion.com)

import base64
import csv
import io

from odoo import fields, models, _
from odoo.exceptions import AccessDenied, UserError
from odoo.tools import float_is_zero, SQL


class L10nFrFecExportWizardXenon(models.TransientModel):
    _inherit = 'l10n_fr.fec.export.wizard'

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_base_domain_cabinet(self):
        """Domaine de base pour les requêtes cabinet."""
        domain = [('company_id', 'in', tuple(self.env.company._accessible_branches().ids))]
        if self.export_type == "official":
            domain.append(('parent_state', '=', 'posted'))
        return domain

    def _do_query_unaffected_earnings_cabinet(self):
        """
        Calcule la somme des soldes de clôture pour les comptes charges/produits
        (qui ne reportent pas le solde en début d'exercice).
        """
        formatted_date_from = fields.Date.to_string(self.date_from).replace('-', '')
        query = self.env['account.move.line']._search(self._get_base_domain_cabinet() + [
            ('date', '<', self.date_from),
            ('account_id.include_initial_balance', '=', False),
        ])
        sql_query = query.select(SQL(
            """
                'OUV' AS JournalCode,
                %(formatted_date_from)s AS EcritureDate,
                '120/129' AS CompteNum,
                'Benefice (perte) reporte(e)' AS EcritureLib,
                replace(CASE WHEN COALESCE(sum(account_move_line.balance), 0) <= 0 THEN '0,00' ELSE to_char(SUM(account_move_line.balance), '000000000000000D99') END, '.', ',') AS Debit,
                replace(CASE WHEN COALESCE(sum(account_move_line.balance), 0) >= 0 THEN '0,00' ELSE to_char(-SUM(account_move_line.balance), '000000000000000D99') END, '.', ',') AS Credit,
                '-' AS PieceRef,
                '' AS EcritureLet
            """,
            formatted_date_from=formatted_date_from,
        ))
        self.env.flush_all()
        self._cr.execute(sql_query)
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

    def _csv_write_rows_cabinet(self, rows, lineterminator='\r\n'):
        """Écrit les lignes dans un fichier CSV avec séparateur pipe."""
        fecfile = io.BytesIO()
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

    # -------------------------------------------------------------------------
    # Méthode principale
    # -------------------------------------------------------------------------

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

        # _field_to_sql pour le nom du compte (sans query = pas de code_store)
        aa_name = self.env['account.account']._field_to_sql('account_move_line__account_id', 'name')

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

        # ---------------------------------------------------------------
        # SOLDES INITIAUX - résultat exercice précédent
        # ---------------------------------------------------------------
        unaffected_earnings_account = self.env['account.account'].search([
            *self.env['account.account']._check_company_domain(company),
            ('account_type', '=', 'equity_unaffected'),
        ], limit=1)
        unaffected_earnings_line = True
        unaffected_earnings_results = []
        if unaffected_earnings_account:
            unaffected_earnings_results = self._do_query_unaffected_earnings_cabinet()
            unaffected_earnings_line = False

        # ---------------------------------------------------------------
        # SOLDES INITIAUX - comptes hors tiers
        # ---------------------------------------------------------------
        query = self.env['account.move.line']._search(self._get_base_domain_cabinet() + [
            ('date', '<', self.date_from),
            ('account_id.include_initial_balance', '=', True),
            ('account_id.account_type', 'not in', ['asset_receivable', 'liability_payable']),
        ])
        aa_code = self.env['account.account']._field_to_sql('account_move_line__account_id', 'code', query)
        sql_query = query.select(SQL(
            """
                'OUV' AS JournalCode,
                %(formatted_date_from)s AS EcritureDate,
                MIN(%(aa_code)s) AS CompteNum,
                replace(replace(MIN(%(aa_name)s), '|', ''), E'\\t', '') AS EcritureLib,
                replace(CASE WHEN sum(account_move_line.balance) <= 0 THEN '0,00' ELSE to_char(SUM(account_move_line.balance), '000000000000000D99') END, '.', ',') AS Debit,
                replace(CASE WHEN sum(account_move_line.balance) >= 0 THEN '0,00' ELSE to_char(-SUM(account_move_line.balance), '000000000000000D99') END, '.', ',') AS Credit,
                '-' AS PieceRef,
                '' AS EcritureLet,
                MIN(account_move_line__account_id.id) AS CompteID
            """,
            formatted_date_from=formatted_date_from,
            aa_code=aa_code,
            aa_name=aa_name,
        ))
        self.env.flush_all()
        self._cr.execute(SQL(
            '%s GROUP BY account_move_line__account_id.id HAVING round(sum(account_move_line.balance), %s) != 0',
            sql_query, currency_digits
        ))
        for row in self._cr.fetchall():
            listrow = list(row)
            account_id = listrow.pop()
            if not unaffected_earnings_line:
                account = self.env['account.account'].browse(account_id)
                if account.account_type == 'equity_unaffected':
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
                [('account_type', '=', 'equity_unaffected'), ('company_id', '=', company.id)], limit=1)
            if unaffected_account:
                unaffected_earnings_results[2] = unaffected_account.code
            rows_to_write.append(unaffected_earnings_results)

        # ---------------------------------------------------------------
        # SOLDES INITIAUX - comptes tiers (receivable/payable)
        # ---------------------------------------------------------------
        query = self.env['account.move.line']._search(self._get_base_domain_cabinet() + [
            ('date', '<', self.date_from),
            ('account_id.include_initial_balance', '=', True),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
        ])
        query.left_join('account_move_line', 'partner_id', 'res_partner', 'id', 'partner_id')
        aa_code = self.env['account.account']._field_to_sql('account_move_line__account_id', 'code', query)
        sql_query = query.select(SQL(
            """
                'OUV' AS JournalCode,
                %(formatted_date_from)s AS EcritureDate,
                CASE WHEN account_move_line__partner_id.id IS NULL
                     THEN MIN(%(aa_code)s)
                     ELSE MIN(%(aa_code)s) || '_' || account_move_line__partner_id.id
                END AS CompteNum,
                COALESCE(replace(account_move_line__partner_id.name, '|', '-'), MIN(%(aa_name)s)) AS EcritureLib,
                replace(CASE WHEN sum(account_move_line.balance) <= 0 THEN '0,00' ELSE to_char(SUM(account_move_line.balance), '000000000000000D99') END, '.', ',') AS Debit,
                replace(CASE WHEN sum(account_move_line.balance) >= 0 THEN '0,00' ELSE to_char(-SUM(account_move_line.balance), '000000000000000D99') END, '.', ',') AS Credit,
                '-' AS PieceRef,
                '' AS EcritureLet
            """,
            formatted_date_from=formatted_date_from,
            aa_code=aa_code,
            aa_name=aa_name,
        ))
        self.env.flush_all()
        self._cr.execute(SQL(
            '%s GROUP BY account_move_line__account_id.id, account_move_line__partner_id.id HAVING round(sum(account_move_line.balance), %s) != 0',
            sql_query, currency_digits
        ))
        for row in self._cr.fetchall():
            rows_to_write.append(list(row))

        # ---------------------------------------------------------------
        # ÉCRITURES DE LA PÉRIODE - hors CABA
        # ---------------------------------------------------------------
        query = self.env['account.move.line']._search(self._get_base_domain_cabinet() + [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('journal_id.code', '!=', 'CABA'),
        ])
        account_alias = query.join('account_move_line', 'account_id', 'account_account', 'id', 'account_id')
        aa_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
        aa_name_lines = self.env['account.account']._field_to_sql(account_alias, 'name')
        move_alias = SQL.identifier(query.left_join('account_move_line', 'move_id', 'account_move', 'id', 'move_id'))
        journal_alias = SQL.identifier(query.left_join('account_move_line', 'journal_id', 'account_journal', 'id', 'journal_id'))
        partner_alias = SQL.identifier(query.left_join('account_move_line', 'partner_id', 'res_partner', 'id', 'partner_id'))
        rec_alias = SQL.identifier(query.left_join('account_move_line', 'full_reconcile_id', 'account_full_reconcile', 'id', 'full_reconcile_id'))

        columns = SQL(
            """
                replace(replace(replace(replace(%(journal_alias)s.code, '|', '-'), E'\\t', ''), 'FACTU', 'AC'), 'FAC', 'VE') AS JournalCode,
                TO_CHAR(%(move_alias)s.date, 'YYYYMMDD') AS EcritureDate,
                CASE WHEN %(account_alias)s.account_type IN ('asset_receivable', 'liability_payable') THEN
                    CASE WHEN %(partner_alias)s.id IS NULL THEN %(aa_code)s ELSE %(aa_code)s || '_' || %(partner_alias)s.id END
                ELSE %(aa_code)s END AS CompteNum,
                COALESCE(
                    replace(replace(%(partner_alias)s.name, '|', '-'), E'\\t', ''),
                    replace(replace(replace(replace(replace(account_move_line.name, '|', '-'), E'\\t', ''), E'\\n', ''), E'\\r', ''), ';', ''),
                    %(aa_name_lines)s
                ) AS EcritureLib,
                replace(CASE WHEN account_move_line.debit = 0 THEN '0,00' ELSE to_char(account_move_line.debit, '000000000000000D99') END, '.', ',') AS Debit,
                replace(CASE WHEN account_move_line.credit = 0 THEN '0,00' ELSE to_char(account_move_line.credit, '000000000000000D99') END, '.', ',') AS Credit,
                substring(replace(replace(%(move_alias)s.name, '|', '-'), E'\\t', ''), position('/' in %(move_alias)s.name) + 1, 20) AS PieceRef,
                CASE WHEN %(rec_alias)s.id IS NULL THEN ''::text ELSE %(rec_alias)s.id::text END AS EcritureLet
            """,
            journal_alias=journal_alias,
            move_alias=move_alias,
            partner_alias=partner_alias,
            account_alias=SQL.identifier(account_alias),
            rec_alias=rec_alias,
            aa_code=aa_code,
            aa_name_lines=aa_name_lines,
        )
        self.env.flush_all()
        self._cr.execute(query.select(columns))
        for row in self._cr.fetchall():
            rows_to_write.append(list(row))

        # ---------------------------------------------------------------
        # ÉCRITURES DE LA PÉRIODE - comptes 445 via journal CABA
        # ---------------------------------------------------------------
        query_caba = self.env['account.move.line']._search([
            ('company_id', 'in', tuple(self.env.company._accessible_branches().ids)),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('journal_id.code', '=', 'CABA'),
            ('account_id.code', 'like', '445%'),
        ])
        account_alias_c = query_caba.join('account_move_line', 'account_id', 'account_account', 'id', 'account_id')
        aa_code_c = self.env['account.account']._field_to_sql(account_alias_c, 'code', query_caba)
        aa_name_c = self.env['account.account']._field_to_sql(account_alias_c, 'name')
        move_alias_c = SQL.identifier(query_caba.left_join('account_move_line', 'move_id', 'account_move', 'id', 'move_id'))
        journal_alias_c = SQL.identifier(query_caba.left_join('account_move_line', 'journal_id', 'account_journal', 'id', 'journal_id'))
        partner_alias_c = SQL.identifier(query_caba.left_join('account_move_line', 'partner_id', 'res_partner', 'id', 'partner_id'))
        rec_alias_c = SQL.identifier(query_caba.left_join('account_move_line', 'full_reconcile_id', 'account_full_reconcile', 'id', 'full_reconcile_id'))

        columns_caba = SQL(
            """
                replace(replace(replace(replace(%(journal_alias)s.code, '|', '-'), E'\\t', ''), 'FACTU', 'AC'), 'FAC', 'VE') AS JournalCode,
                TO_CHAR(%(move_alias)s.date, 'YYYYMMDD') AS EcritureDate,
                %(aa_code)s AS CompteNum,
                COALESCE(
                    replace(replace(%(partner_alias)s.name, '|', '-'), E'\\t', ''),
                    replace(replace(replace(replace(replace(account_move_line.name, '|', '-'), E'\\t', ''), E'\\n', ''), E'\\r', ''), ';', ''),
                    %(aa_name)s
                ) AS EcritureLib,
                replace(CASE WHEN account_move_line.debit = 0 THEN '0,00' ELSE to_char(account_move_line.debit, '000000000000000D99') END, '.', ',') AS Debit,
                replace(CASE WHEN account_move_line.credit = 0 THEN '0,00' ELSE to_char(account_move_line.credit, '000000000000000D99') END, '.', ',') AS Credit,
                substring(replace(replace(%(move_alias)s.name, '|', '-'), E'\\t', ''), position('/' in %(move_alias)s.name) + 1, 20) AS PieceRef,
                CASE WHEN %(rec_alias)s.id IS NULL THEN ''::text ELSE %(rec_alias)s.id::text END AS EcritureLet
            """,
            journal_alias=journal_alias_c,
            move_alias=move_alias_c,
            partner_alias=partner_alias_c,
            rec_alias=rec_alias_c,
            aa_code=aa_code_c,
            aa_name=aa_name_c,
        )
        self.env.flush_all()
        self._cr.execute(query_caba.select(columns_caba))
        for row in self._cr.fetchall():
            rows_to_write.append(list(row))

        # ---------------------------------------------------------------
        # Écriture du fichier
        # ---------------------------------------------------------------
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
