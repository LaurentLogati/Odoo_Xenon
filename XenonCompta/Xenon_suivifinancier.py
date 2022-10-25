#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Copyright (C) 2013-2015 Akretion (http://www.akretion.com)

import base64
import io

import logging
_logger = logging.getLogger(__name__)

from odoo import api, fields, models, _
from odoo.exceptions import Warning
from odoo.tools import float_is_zero, pycompat


class XenonSuiviFinancier(models.TransientModel):
    _name = 'x.suivifinancier'
    _description = 'Suivi financier Xenon'

    x_date_from = fields.Date(string='Start Date', required=True)
    x_date_to = fields.Date(string='End Date', required=True)
    x_fec_data = fields.Binary('FEC File', readonly=True, attachment=False)
    x_filename = fields.Char(string='Filename', size=256, readonly=True)
    x_export_type = fields.Selection([
        ('official', 'Official FEC report (posted entries only)'),
        ('nonofficial', 'Non-official FEC report (posted and unposted entries)'),
        ], string='Export Type', required=True, default='official')
    
    def do_query_test_export(self):
        self.ensure_one()
        if not (self.env.is_admin() or self.env.user.has_group('account.group_account_user')):
            raise AccessDenied()
        
        company = self.env.company
        
        
        header = [
            u'id',    # 0
            u'libellepiece',     # 1
            u'datepiece',    # 2
            u'textefin',   # 3
            ]

        rows_to_write = [header]
        
        sql_query = '''
        Select id, name, date_from, 'textefinal' from public.account_fiscal_year '''
        
        
        self._cr.execute(
            sql_query, (self.x_date_from, self.x_date_to, company.id))

        for row in self._cr.fetchall():
            #_logger.info('logLLO_1' + str(list(row)))
            rows_to_write.append(list(row))
            
        #for row in self._cr.fetchall():
        #    listrow = list(row)
        #    account_id = listrow.pop()
        #    rows_to_write.append(listrow)

        fecvalue = self._csv_write_rows(rows_to_write)
        end_date = fields.Date.to_string(self.x_date_to).replace('-', '')
        suffix = ''
        if self.x_export_type == "nonofficial":
            suffix = '-NONOFFICIAL'

        self.write({
            'x_fec_data': base64.encodestring(fecvalue),
            # Filename = <siren>FECYYYYMMDD where YYYMMDD is the closing date
            'x_filename': '%sLLO%s%s.csv' % (company['name'],end_date, suffix),
            })

        action = {
            'name': 'SuiviFinancier',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=x.suivifinancier&id=" + str(self.id) + "&filename_field=x_filename&field=x_fec_data&download=true&x_filename=" + self.x_filename,
            'target': 'self',
            }
        return action
    
    
    
    ####################################### Export Suivi Financier SF #######################################
    # Pour le journal CABA (écritures de contrepassation des tva sur encaissement), on ne prend en compte que les comptes de TVA pour simplifier la révision des comptes
    
    def do_query_unaffected_earnings_SF(self):
        ''' Compute the sum of ending balances for all accounts that are of a type that does not bring forward the balance in new fiscal years.
            This is needed because we have to display only one line for the initial balance of all expense/revenue accounts in the FEC.
        '''

        sql_query = '''
        SELECT
            'LLO' AS JournalCode,
            %s AS EcritureDate,
            '120/129' AS CompteNum,
            'RESULTAT EXERCICE' AS EcritureLib,
            replace(CASE WHEN COALESCE(sum(aml.balance), 0) <= 0 THEN '0,00' ELSE to_char(SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Debit,
            replace(CASE WHEN COALESCE(sum(aml.balance), 0) >= 0 THEN '0,00' ELSE to_char(-SUM(aml.balance), '000000000000000D99') END, '.', ',') AS Credit,
            '-' AS PieceRef,
            '' AS EcritureLet,
            '' AS textefin
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id=aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN account_account_type aat ON aa.user_type_id = aat.id
        WHERE
            am.date < %s
            AND am.company_id = %s
            AND aat.include_initial_balance IS NOT TRUE
            AND (aml.debit != 0 OR aml.credit != 0)
        '''
        # For official report: only use posted entries
        if self.x_export_type == "official":
            sql_query += '''
            AND am.state = 'posted'
            '''
        company = self.env.company
        formatted_date_from = fields.Date.to_string(self.x_date_from).replace('-', '')
        x_date_from = self.x_date_from
        formatted_date_year = x_date_from.year
        self._cr.execute(
            sql_query, (formatted_date_from, self.x_date_from, company.id))
        listrow = []
        row = self._cr.fetchone()
        listrow = list(row)
        return listrow
    
    
    def _get_company_legal_data_SF(self, company):
        """
        Dom-Tom are excluded from the EU's fiscal territory
        Those regions do not have SIREN
        sources:
            https://www.service-public.fr/professionnels-entreprises/vosdroits/F23570
            http://www.douane.gouv.fr/articles/a11024-tva-dans-les-dom
        """
        dom_tom_group = self.env.ref('l10n_fr.dom-tom')
        is_dom_tom = company.country_id.code in dom_tom_group.country_ids.mapped('code')
        if not is_dom_tom and not company.vat:
            raise Warning(
                _("Missing VAT number for company %s") % company.name)
        if not is_dom_tom and company.vat[0:2] != 'FR':
            raise Warning(
                _("FEC is for French companies only !"))

        return {
            'siren': company.vat[4:13] if not is_dom_tom else '',
        }
    
    
    
    def generate_export_suivifinancier_xenon(self):
        self.ensure_one()
        # We choose to implement the flat file instead of the XML
        # file for 2 reasons :
        # 1) the XSD file impose to have the label on the account.move
        # but Odoo has the label on the account.move.line, so that's a
        # problem !
        # 2) CSV files are easier to read/use for a regular accountant.
        # So it will be easier for the accountant to check the file before
        # sending it to the fiscal administration
        company = self.env.company
        #company_legal_data = self._get_company_legal_data_SF(company)

        header = [
            u'JournalCode',    # 0
            u'EcritureDate',   # 1
            u'CompteNum',      # 2
            u'CompteLib',      # 3
            u'EcritureLib',    # 4
            u'Debit',          # 5
            u'Credit',         # 6
            u'Balance',        # 7
            u'PieceRef',       # 8
            u'EcritureLet',    # 9
            u'CatResBilan',    # 10
            u'Societe',        # 11
            u'Exercice',       # 12
            u'Tiers',          # 13
            u'TiersID',        # 14 agId juste pour info-----
            u'CodeAna',        # 15
            u'Affaire',        # 16
            u'CodeAtelier',        # 17
            u'Atelier',        # 18
            u'Idclientliv',        # 19
            u'Clientliv',        # 20
            u'Devisclient',        # 21
            u'Id_article',        # 22
            u'Default_code',        # 23
            u'id2_article',        # 24
            u'article',        # 25
            u'typearticle',        # 26
            u'idmove',        # 27
            u'ref',        # 28
            u'state',        # 29
            u'type',        # 30
            u'invoice_origin',        # 31
            u'invoice_partner_display_name',        # 32
            u'idmoveline',        # 33
            u'sequence',        # 34
            u'name',        # 35
            u'quantity',        # 36
            u'price_unit',        # 37
            u'discount',        # 38
            u'price_subtotal',        # 39
            u'display_type',        # 40---
            u'SensBalance',    # 41
            u'SensSoldeTiers', # 42
            u'AnneeMois',      # 43
            u'DebitBudget',    # 44
            u'CreditBudget',   # 45
            u'MontantBudget',  # 46
            u'Etat',           # 47
            u'TypeLigne',      # 48
            u'SIG',            # 49
            u'MontantM',       # 50
            u'NomBudget',      # 51
            u'CompteClasse',   # 52
            u'CompteType',     # 53
            u'textefin',       # 54
            ]

        rows_to_write = [header]
        # INITIAL BALANCE
        unaffected_earnings_xml_ref = self.env.ref('account.data_unaffected_earnings')
        unaffected_earnings_line = True  # used to make sure that we add the unaffected earning initial balance only once
        if unaffected_earnings_xml_ref:
            #compute the benefit/loss of last year to add in the initial balance of the current year earnings account
            #LLO 25/01/2022 
            unaffected_earnings_results = self.do_query_unaffected_earnings_SF()
            unaffected_earnings_line = False

        sql_query = '''
        
        WITH
        InitialBalance as (
        SELECT
            'OUV' AS JournalCode,
            EF.date_from AS EcritureDate,
            MIN(aa.code) AS CompteNum,
            replace(replace(MIN(aa.name), '|', ''), '\t', '') AS CompteLib,
            replace(replace(MIN(aa.name), '|', ''), '\t', '') AS EcritureLib,
            CASE WHEN sum(aml.balance) <= 0 THEN 0 ELSE SUM(aml.balance) END AS Debit,
            CASE WHEN sum(aml.balance) >= 0 THEN 0 ELSE -SUM(aml.balance) END AS Credit, 
            SUM(aml.balance) AS Balance, 
            '-' AS PieceRef,
            '' AS EcritureLet,
            case when ag.name is null then '' else ag.name end AS CatResBilan,
            rcomp.name as Societe,
            EF.name as Exercice,
            '' AS Tiers,
            0 AS TiersID,
            0 as agId,
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as  article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            0 as quantity,
            0 as price_unit,
            0 as discount,
            0 as price_subtotal,
            '' as display_type,
            'Realise' as NomBudget, 
            substring(MIN(aa.code),1,1) as CompteClasse,
            MIN(aat.name) as CompteType

        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id=aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN account_account_type aat ON aa.user_type_id = aat.id
            LEFT JOIN account_group ag ON ag.id=aa.group_id
            INNER JOIN res_company rcomp on rcomp.id=am.company_id
            inner join account_fiscal_year EF on EF.company_id=rcomp.id and am.date < EF.date_from
        WHERE
            aat.include_initial_balance = 't'
            AND (aml.debit != 0 OR aml.credit != 0)
            and aat.name!='Current Year Earnings'
        '''
            
        # For official report: only use posted entries
        if self.x_export_type == "official":
            sql_query += '''
            AND am.state = 'posted'
            '''

        sql_query += '''
        GROUP BY aml.account_id, aat.type, ag.name, rcomp.name, EF.name, EF.date_from
        HAVING round(sum(aml.balance), 2) != 0
        AND aat.type not in ('receivable', 'payable'))
        '''
        
        
        

        # INITIAL BALANCE - receivable/payable   
        sql_query += '''
        , InitialBalanceTiers as (
        SELECT
            'OUV' AS JournalCode,
            EF.date_from AS EcritureDate,
            MIN(aa.code) AS CompteNum,
            replace(replace(MIN(aa.name), '|', ''), '\t', '') AS CompteLib,
            CASE WHEN aat.type IN ('receivable', 'payable')
            THEN COALESCE(replace(rp.name, '|', '-'), MIN(aa.name))
            ELSE ''
            END AS EcritureLib,
            CASE WHEN sum(aml.balance) <= 0 THEN 0 ELSE SUM(aml.balance) END AS Debit,
            CASE WHEN sum(aml.balance) >= 0 THEN 0 ELSE -SUM(aml.balance) END AS Credit, 
            SUM(aml.balance) AS Balance, 
            '-' AS PieceRef,
            '' AS EcritureLet,
            case when ag.name is null then '' else ag.name end AS CatResBilan,
            rcomp.name as Societe,
            EF.name as Exercice,
            rp.name as Tiers,
            rp.id AS TiersID,
            0 as agId,
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as  article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            0 as quantity,
            0 as price_unit,
            0 as discount,
            0 as price_subtotal,
            '' as display_type,
            'Realise' as NomBudget, 
            substring(MIN(aa.code),1,1) as CompteClasse,
            MIN(aat.name) as CompteType
            
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id=aml.move_id
            LEFT JOIN res_partner rp ON rp.id=aml.partner_id
            JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN account_account_type aat ON aa.user_type_id = aat.id
            LEFT JOIN account_group ag ON ag.id=aa.group_id
            INNER JOIN res_company rcomp on rcomp.id=am.company_id
            inner join account_fiscal_year EF on EF.company_id=rcomp.id and am.date < EF.date_from
        WHERE
            aat.include_initial_balance = 't'
            AND (aml.debit != 0 OR aml.credit != 0)
            and aat.name!='Current Year Earnings'
        '''
            
        # For official report: only use posted entries
        if self.x_export_type == "official":
            sql_query += '''
            AND am.state = 'posted'
            '''

        sql_query += '''
        GROUP BY aml.account_id, aat.type, rp.ref, rp.id, ag.name, rcomp.name, EF.name, EF.date_from
        HAVING round(sum(aml.balance), 2) != 0
        AND aat.type in ('receivable', 'payable'))
        '''
        
        # Recherche des informations liés au devis client (code analytique, atelier, num devis)
        sql_query += '''
        , AffaireAtelier as (
        Select 
            so.warehouse_id as CodeAtelier, swso.name as Atelier, so.analytic_account_id as codeana, aac.name as affaire, so.company_id as societe, 
            so.partner_id as idclientliv, so.name as devisclient--, so.partner_invoice_id as clientfact
        from sale_order so
        inner join stock_warehouse swso on swso.id=so.warehouse_id
        inner join account_analytic_account aac on aac.id=so.analytic_account_id
        where so.state!='cancel'
        group by so.warehouse_id, swso.name, so.analytic_account_id, aac.name, so.company_id, so.partner_id, so.name--, so.partner_invoice_id
        )
        '''
        
        # Francisation des types d'écritures
        sql_query += '''
        , TypeEcriture as (
        select type as typeO, 
        case when type='entry' then 'ecriture' 
        when type='out_invoice' then 'facture_client' 
        when type='in_invoice' then 'facture_frs'
        when type='out_refund' then 'avoir_client'
        when type='in_refund' then 'avoir_frs'
        else 'autre' end as typeF
        from account_move
        group by type
        )
        '''

        # Libellé écriture ==> 1- libellé partenaire 2- libellé écriture 3- libellé compte
        # substring(replace(replace(am.name, '|', '-'), '\t', ''), position('/' in am.name)+1, 10) AS PieceRef,
        sql_query += '''
        , Ecritures as (
        SELECT
            replace(replace(replace(replace(aj.code, '|', '-'), '\t', ''),'FACTU','AC'),'FAC','VE') AS JournalCode,
            am.date AS EcritureDate,
            aa.code AS CompteNum,
            aa.name AS CompteLib,
            coalesce(replace(replace(rp.name, '|', '-'), '\t', ''), replace(replace(replace(replace(replace(aml.name, '|', '-'), '\t', ''), '\n', ''), '\r', ''),';',''),aa.name) AS EcritureLib, 
            CASE WHEN sum(aml.balance) <= 0 THEN 0 ELSE SUM(aml.balance) END AS Debit,
            CASE WHEN sum(aml.balance) >= 0 THEN 0 ELSE -SUM(aml.balance) END AS Credit, 
            sum(aml.balance) AS Balance, 
            replace(replace(am.name, '|', '-'), '\t', '') AS PieceRef,
            CASE WHEN rec.name IS NULL THEN '' ELSE rec.name END AS EcritureLet,
            case when ag.name is null then '' else ag.name end AS CatResBilan,
            rcomp.name as Societe,
            EF.name as Exercice,
            rp.name as Tiers,
            rp.id AS TiersID,
            ag.id as agId,
			case when coalesce(aac.id, affat.codeana) is null then 0 else coalesce(aac.id, affat.codeana) end as codeana, 
			case when coalesce(aac.name, affat.affaire) is null then 'SansCodeAnalytique' else coalesce(aac.name, affat.affaire) end as affaire,
			coalesce(so.warehouse_id, swpo.id, affat.CodeAtelier) as CodeAtelier, coalesce(swso.name, swpo.name, affat.Atelier) as Atelier,
			affat.idclientliv as idclientliv, rpliv.name as clientliv, affat.devisclient as devisclient, --, affat.clientfact,
			--am.partner_shipping_id as idclientliv, am.partner_id as idclientfact, rpliv.name as clientliv,
			pp.id as id_article, pp.default_code, pt.id as id2_article, pt.name as article, pt.type as typearticle,
			am.id as idmove, replace(replace(am.ref,';',''),',','') as ref, am.state, 
            te.typeF, 
            am.invoice_origin, am.invoice_partner_display_name,
			aml.id as idmoveline, aml.sequence, replace(replace(replace(aml.name,chr(10),''),';',''),',','') as name,
			aml.quantity, aml.price_unit, aml.discount, aml.price_subtotal, aml.display_type,
            'Realise' as NomBudget, 
            substring(aa.code,1,1) as CompteClasse,
            aat.name as CompteType
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id=aml.move_id
            LEFT JOIN res_partner rp ON rp.id=aml.partner_id
            JOIN account_journal aj ON aj.id = am.journal_id
            JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN account_account_type aat ON aa.user_type_id = aat.id
            LEFT JOIN res_currency rc ON rc.id = aml.currency_id
            LEFT JOIN account_full_reconcile rec ON rec.id = aml.full_reconcile_id
            LEFT JOIN account_group ag ON ag.id=aa.group_id
            INNER JOIN res_company rcomp on rcomp.id=am.company_id
            INNER JOIN account_fiscal_year EF on EF.company_id=rcomp.id and am.date between EF.date_from and EF.date_to
			left join account_analytic_account aac on aac.id=aml.analytic_account_id
			left join sale_order so on so.name=am.invoice_origin and so.company_id=am.company_id and so.state!='cancel'
			left join purchase_order po on po.name=am.invoice_origin and po.company_id=am.company_id and po.state!='cancel'
			left join stock_warehouse swso on swso.id=so.warehouse_id and swso.company_id=so.company_id
			left join stock_picking_type spt on spt.id=po.picking_type_id and spt.company_id=po.company_id
			left join stock_warehouse swpo on swpo.id=spt.warehouse_id  and swpo.company_id=spt.company_id
			left join AffaireAtelier affat on affat.codeana=aac.id and affat.societe=am.company_id and affat.devisclient=po.origin
			left join product_product pp on pp.id=aml.product_id
			left join product_template pt on pt.id =pp.product_tmpl_id
			left join res_partner rpliv ON rpliv.id=so.partner_id--am.partner_shipping_id
            left join TypeEcriture te on te.typeO=am.type
            
        WHERE
            am.date >= %s
            AND am.date <= %s
            AND (aml.debit != 0 OR aml.credit != 0)
            and aj.code!='CABA'
            and aat.name!='Current Year Earnings'
        '''
            #AND am.company_id = %s

        # For official report: only use posted entries
        if self.x_export_type == "official":
            sql_query += '''
            AND am.state = 'posted'
            '''
            
        sql_query += '''
        GROUP BY
            JournalCode, EcritureDate, CompteNum, CompteLib, EcritureLib, PieceRef, EcritureLet, 
            CatResBilan, rcomp.name, Exercice, Tiers, TiersID, agId, 
			aac.id, affat.codeana, aac.name, affat.affaire,
			so.warehouse_id, swpo.id, affat.CodeAtelier, swso.name, swpo.name, affat.Atelier,
			affat.idclientliv, rpliv.name, affat.devisclient,
			--am.partner_shipping_id, am.partner_id, rpliv.name,
			pp.id, pp.default_code, pt.id, pt.name, pt.type,
			am.id, am.ref, am.state, am.type, te.typeF, am.invoice_origin, am.invoice_partner_display_name,
			aml.id, aml.sequence, aml.name,
			aml.quantity, aml.price_unit, aml.discount, aml.price_subtotal, aml.display_type,
            aat.name
        UNION ALL
        SELECT
            replace(replace(replace(replace(aj.code, '|', '-'), '\t', ''),'FACTU','AC'),'FAC','VE') AS JournalCode,
            am.date AS EcritureDate,
            aa.code AS CompteNum,
            aa.name AS CompteLib,
            coalesce(replace(replace(rp.name, '|', '-'), '\t', ''), replace(replace(replace(replace(replace(aml.name, '|', '-'), '\t', ''), '\n', ''), '\r', ''),';',''),aa.name) AS EcritureLib, 
            CASE WHEN sum(aml.balance) <= 0 THEN 0 ELSE SUM(aml.balance) END AS Debit,
            CASE WHEN sum(aml.balance) >= 0 THEN 0 ELSE -SUM(aml.balance) END AS Credit, 
            sum(aml.balance) AS Balance, 
            replace(replace(am.name, '|', '-'), '\t', '') AS PieceRef,
            CASE WHEN rec.name IS NULL THEN '' ELSE rec.name END AS EcritureLet,
            case when ag.name is null then '' else ag.name end AS CatResBilan,
            rcomp.name as Societe,
            EF.name as Exercice,
            rp.name as Tiers,
            rp.id AS TiersID,
            ag.id as agId,
			case when coalesce(aac.id, affat.codeana) is null then 0 else coalesce(aac.id, affat.codeana) end as codeana, 
			case when coalesce(aac.name, affat.affaire) is null then 'SansCodeAnalytique' else coalesce(aac.name, affat.affaire) end as affaire,
			coalesce(so.warehouse_id, swpo.id, affat.CodeAtelier) as CodeAtelier, coalesce(swso.name, swpo.name, affat.Atelier) as Atelier,
			affat.idclientliv as idclientliv, rpliv.name as clientliv, affat.devisclient as devisclient, --, affat.clientfact,
			--am.partner_shipping_id as idclientliv, am.partner_id as idclientfact, rpliv.name as clientliv,
			pp.id as id_article, pp.default_code, pt.id as id2_article, pt.name as article, pt.type as typearticle,
			am.id as idmove, replace(replace(am.ref,';',''),',','') as ref, am.state, 
            te.typeF, 
            am.invoice_origin, am.invoice_partner_display_name,
			aml.id as idmoveline, aml.sequence, replace(replace(replace(aml.name,chr(10),''),';',''),',','') as name,
			aml.quantity, aml.price_unit, aml.discount, aml.price_subtotal, aml.display_type,
            'Realise' as NomBudget, 
            substring(aa.code,1,1) as CompteClasse,
            aat.name as CompteType
        FROM
            account_move_line aml
            LEFT JOIN account_move am ON am.id=aml.move_id
            LEFT JOIN res_partner rp ON rp.id=aml.partner_id
            JOIN account_journal aj ON aj.id = am.journal_id
            JOIN account_account aa ON aa.id = aml.account_id and substring(aa.code,1,3)='445'
            LEFT JOIN account_account_type aat ON aa.user_type_id = aat.id
            LEFT JOIN res_currency rc ON rc.id = aml.currency_id
            LEFT JOIN account_full_reconcile rec ON rec.id = aml.full_reconcile_id
            LEFT JOIN account_group ag ON ag.id=aa.group_id
            INNER JOIN res_company rcomp on rcomp.id=am.company_id
            INNER JOIN account_fiscal_year EF on EF.company_id=rcomp.id and am.date between EF.date_from and EF.date_to
            
            left join account_analytic_account aac on aac.id=aml.analytic_account_id
			left join sale_order so on so.name=am.invoice_origin and so.company_id=am.company_id and so.state!='cancel'
			left join purchase_order po on po.name=am.invoice_origin and po.company_id=am.company_id and po.state!='cancel'
			left join stock_warehouse swso on swso.id=so.warehouse_id and swso.company_id=so.company_id
			left join stock_picking_type spt on spt.id=po.picking_type_id and spt.company_id=po.company_id
			left join stock_warehouse swpo on swpo.id=spt.warehouse_id  and swpo.company_id=spt.company_id
			left join AffaireAtelier affat on affat.codeana=aac.id and affat.societe=am.company_id and affat.devisclient=po.origin
			left join product_product pp on pp.id=aml.product_id
			left join product_template pt on pt.id =pp.product_tmpl_id
			left join res_partner rpliv ON rpliv.id=so.partner_id--am.partner_shipping_id
            left join TypeEcriture te on te.typeO=am.type
        WHERE
            am.date >= %s
            AND am.date <= %s
            AND (aml.debit != 0 OR aml.credit != 0)
            AND am.state = 'posted'
			AND aj.code='CABA'
            AND aat.name!='Current Year Earnings'
        '''
            #AND am.company_id = %s
        
         # For official report: only use posted entries
        if self.x_export_type == "official":
            sql_query += '''
            AND am.state = 'posted'
            '''

        sql_query += '''
        GROUP BY
            JournalCode, EcritureDate, CompteNum, CompteLib, EcritureLib, PieceRef, EcritureLet, 
            CatResBilan, rcomp.name, Exercice, Tiers, TiersID, agId,
            aac.id, affat.codeana, aac.name, affat.affaire,
			so.warehouse_id, swpo.id, affat.CodeAtelier, swso.name, swpo.name, affat.Atelier,
			affat.idclientliv, rpliv.name, affat.devisclient,
			--am.partner_shipping_id, am.partner_id, rpliv.name,
			pp.id, pp.default_code, pt.id, pt.name, pt.type,
			am.id, am.ref, am.state, am.type, te.typeF, am.invoice_origin, am.invoice_partner_display_name,
			aml.id, aml.sequence, aml.name,
			aml.quantity, aml.price_unit, aml.discount, aml.price_subtotal, aml.display_type,
            aat.name
        ORDER BY
            EcritureDate,
			JournalCode,
            PieceRef)
            
        , Resultat1 as (
            SELECT * from InitialBalance
            UNION ALL
            SELECT * from InitialBalanceTiers
            UNION ALL
            SELECT * from Ecritures)
        
        , Balance as (
        SELECT Societe, CompteNum, Exercice, SUM(Balance) AS Montant
        FROM Resultat1
        GROUP BY Societe, CompteNum, Exercice)
        
        , SoldeTiers as (
        SELECT Societe, CompteNum, Exercice, Tiers, TiersID, SUM(Balance) AS Montant
        FROM Resultat1 R1
        INNER JOIN account_account aa ON aa.code = R1.CompteNum
        LEFT JOIN account_account_type aat ON aa.user_type_id = aat.id
        WHERE aat.type in ('receivable', 'payable')
        GROUP BY Societe, CompteNum, Exercice, Tiers, TiersID
        )
        
               
        ,Company as
		(Select id, name from public.res_company)

	,ExerciceFiscal as
		(Select id, name, date_from, date_to, company_id from public.account_fiscal_year)

	,BudgetEnLigne as (
		select B0.x_company_id, B0.x_libelle as Budget, 
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut,'YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut,'DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '1 month - 1 day','DD/MM/YYYY') as MoisFin, B1.x_compte, B1.x_montant_1 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		union
		select B0.x_company_id, B0.x_libelle as Budget, 
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '1 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '1 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '2 month - 1 day','DD/MM/YYYY') as MoisFin, 
            B1.x_compte, B1.x_montant_2 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '1 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget, 
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '2 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '2 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '3 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_3 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '2 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '3 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '3 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '4 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_4 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '3 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '4 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '4 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '5 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_5 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '4 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '5 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '5 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '6 month - 1 day','DD/MM/YYYY') as MoisFin, 
            B1.x_compte, B1.x_montant_6 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '5 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget, 
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '6 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '6 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '7 month - 1 day','DD/MM/YYYY') as MoisFin, 
            B1.x_compte, B1.x_montant_7 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '6 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '7 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '7 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '8 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_8 as Montant
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '7 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '8 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '8 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '9 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_9 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '8 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget, 
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '9 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '9 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '10 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_10 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '9 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '10 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '10 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '11 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_11 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '10 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '11 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '11 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '12 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_12 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '11 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice, B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '12 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '12 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '13 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_13 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '12 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget, 
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '13 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '13 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '14 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_14 as Montant
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '13 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '14 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '14 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '15 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_15 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '14 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '15 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '15 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '16 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_16 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '15 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '16 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '16 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '17 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_17 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '16 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '17 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '17 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '18 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_18 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '17 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '18 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '18 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '19 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_19 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '18 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '19 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '19 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '20 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_20 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '19 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '20 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '20 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '21 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_21 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '20 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '21 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '21 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '22 month - 1 day','DD/MM/YYYY') as MoisFin, 
            B1.x_compte, B1.x_montant_22 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '21 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '22 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '22 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '23 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_23 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '22 month') < B0.x_datefin
		union
		select B0.x_company_id, B0.x_libelle as Budget,
            coalesce(B0.x_exercice,EF.name) as Exercice,
            B0.x_datedebut as DateDebut, B0.x_datefin as DateFin, B0.x_statut as Statut, 
            to_char(B0.x_datedebut + INTERVAL '23 month','YYYY-MM') as AnneeMois,
            to_char(B0.x_datedebut + INTERVAL '23 month','DD/MM/YYYY') as MoisDebut, to_char(B0.x_datedebut + INTERVAL '24 month - 1 day','DD/MM/YYYY') as MoisFin,
            B1.x_compte, B1.x_montant_24 as Montant 
		from x_budget B0
		inner join x_budget_detail B1 on B1.x_liste_ids=B0.id
        left join ExerciceFiscal EF on EF.company_id=B0.x_company_id and EF.date_from<=B0.x_datedebut and EF.date_to>=B0.x_datedebut
		where (B0.x_datedebut + INTERVAL '23 month') < B0.x_datefin
		)

	,Budget as (select B0.Budget as Budget, B0.DateDebut as DateDebut, B0.DateFin as DateFin,
		 C0.code as Compte, C0.name as LibelleCompte, case when C1.name is null then '' else C1.name end AS CatResBilan,
		 B0.MoisDebut as MoisDebut, B0.MoisFin as MoisFin, 
         case substring(C0.code,1,1) when '7' then B0.Montant 
                                     when '6' then B0.Montant * (-1) 
                                     else B0.Montant 
                                     end as Montant         
		, B0.AnneeMois as AnneeMois
		, S0.name as Societe
		, B0.Exercice as Exercice
		, case B0.Statut when 'posted' then 'Budget validé' 
						when 'draft' then 'Budget Brouillon' 
						else B0.Statut 
						end as Etat
		, C1.name as GroupeCompte
        , C1.id as agId,
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as  article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            0 as quantity,
            0 as price_unit,
            0 as discount,
            0 as price_subtotal,
            '' as display_type,
            B0.Budget as NomBudget, 
            substring(C0.code,1,1) as CompteClasse,
            aat.name as CompteType
        
		  from BudgetEnLigne B0
		 inner join account_account C0 on C0.id=B0.x_compte
		 inner join account_group C1 on C1.id=C0.group_id
		 inner join Company S0 on S0.id=x_company_id
         LEFT JOIN account_account_type aat ON C0.user_type_id = aat.id                                                              
		 where B0.Statut!='cancel'

		 order by B0.Budget, B0.AnneeMois, C0.code, C0.name, C1.name
		)
        
    ,SIG as (
    select
        ag0.id as Id0, ag0.name as Name0, ag1.id as Id1, ag1.name as Name1, ag2.id as Id2, ag2.name as Name2,
        ag3.id as Id3, ag3.name as Name3, ag4.id as Id4, ag4.name as Name4, ag5.id as Id5, ag5.name as Name5
    from account_group ag0
    left join account_group ag1 on ag1.parent_id=ag0.id
    left join account_group ag2 on ag2.parent_id=ag1.id
    left join account_group ag3 on ag3.parent_id=ag2.id
    left join account_group ag4 on ag4.parent_id=ag3.id
    left join account_group ag5 on ag5.parent_id=ag4.id
    where ag0.name='Résultat')
		
	, SuiviDetail as (	
	Select
		'BUD' as JournalCode,
        MoisFin as EcritureDate,
        Compte as CompteNum, 
        LibelleCompte as CompteLib,
        Budget as EcritureLib, 
        0 as Debit,
		0 as Credit,
        0 AS Balance,
        '' as PieceRef,
        '' as EcritureLet,
        CatResBilan, --Poste --GroupeCompte
        Societe,
        Exercice,
        '' as Tiers,
        0 as TiersID,
        
        codeana,
        affaire,
        codeatelier,
        atelier,
        idclientliv,
        clientliv,
        devisclient,
        id_article,
        default_code,
        id2_article,
         article,
        typearticle,
        idmove,
        ref,
        state,
        type,
        invoice_origin,
        invoice_partner_display_name,
        idmoveline,
        sequence,
        name,
        quantity,
        price_unit,
        discount,
        price_subtotal,
        display_type,

        CASE WHEN Montant > 0 THEN '+' ELSE '-' END AS SensBalance,
        CASE WHEN Montant > 0 THEN '+' ELSE '-' END AS SensSoldeTiers,
		AnneeMois,
		case substring(Compte,1,1) 
			when '6' then Montant
			else 0
			end as DebitBudget,
		case substring(Compte,1,1) 
			when '7' then Montant
			else 0
			end as CreditBudget,
		Montant as MontantBudget,
		Etat,
        'Budget' as TypeLigne,
        N5.name5 as SIG5,
		coalesce(N4.name4, N5.name4) as SIG4,
		coalesce(N3.name3, N4.name3, N5.name3) as SIG3,
		coalesce(N2.name2, N3.name2, N4.Name2, N5.Name2) as SIG2,
		coalesce(N1.name1, N2.name1, N3.name1, N4.Name1, N5.Name1) as SIG1,
		coalesce(N0.name0, N1.name0, N2.name0, N3.name0, N4.Name0, N5.Name0) as SIG0,
        case coalesce(N0.name0, N1.name0, N2.name0, N3.name0, N4.Name0, N5.Name0) when 'Résultat' then 'SIG' else '' end as SIG,
        0 AS MontantM,
        NomBudget,
        CompteClasse,
        CompteType,          
        '' AS textefin
	from Budget
    LEFT JOIN SIG N5 on N5.id5=agId
			LEFT JOIN SIG N4 on N4.id4=agId
			LEFT JOIN SIG N3 on N3.id3=agId
			LEFT JOIN SIG N2 on N2.id2=agId
			LEFT JOIN SIG N1 on N1.id1=agId
			LEFT JOIN SIG N0 on N0.id0=agId
    union
        SELECT 
        R1.JournalCode,
        to_char(R1.EcritureDate,'DD/MM/YYYY') as EcritureDate,
        R1.CompteNum, 
        R1.CompteLib,
        R1.EcritureLib, 
        R1.Debit AS Debit,
        R1.Credit AS Credit,
        R1.Balance AS Balance,
        R1.PieceRef,
        R1.EcritureLet,
        R1.CatResBilan,
        R1.Societe,
        R1.Exercice,
        R1.Tiers,
        R1.TiersID,
        
        codeana,
        affaire,
        codeatelier,
        atelier,
        idclientliv,
        clientliv,
        devisclient,
        id_article,
        default_code,
        id2_article,
         article,
        typearticle,
        idmove,
        ref,
        state,
        type,
        invoice_origin,
        invoice_partner_display_name,
        idmoveline,
        sequence,
        name,
        quantity,
        price_unit,
        discount,
        price_subtotal,
        display_type,

        CASE WHEN Bal.Montant > 0 THEN '+' ELSE '-' END AS SensBalance,
        CASE WHEN Soti.Montant > 0 THEN '+' ELSE '-' END AS SensSoldeTiers,
        to_char(R1.EcritureDate,'YYYY-MM') as AnneeMois,
		0 as DebitBudget,
		0 as CreditBudget,
		0 as MontantBudget,
		'Comptabilisé' as Etat,
        'Realise' as TypeLigne,
        N5.name5 as SIG5,
		coalesce(N4.name4, N5.name4) as SIG4,
		coalesce(N3.name3, N4.name3, N5.name3) as SIG3,
		coalesce(N2.name2, N3.name2, N4.Name2, N5.Name2) as SIG2,
		coalesce(N1.name1, N2.name1, N3.name1, N4.Name1, N5.Name1) as SIG1,
		coalesce(N0.name0, N1.name0, N2.name0, N3.name0, N4.Name0, N5.Name0) as SIG0,
        case coalesce(N0.name0, N1.name0, N2.name0, N3.name0, N4.Name0, N5.Name0) when 'Résultat' then 'SIG' else '' end as SIG,
        (R1.Balance * (-1)) AS MontantM,
        NomBudget,
        CompteClasse,
        CompteType,          
        '' AS textefin
        FROM Resultat1 R1
        INNER JOIN Balance Bal on Bal.Societe=R1.Societe AND Bal.CompteNum=R1.CompteNum AND Bal.Exercice=R1.Exercice
        LEFT JOIN SoldeTiers Soti on Soti.Societe=R1.Societe AND Soti.CompteNum=R1.CompteNum AND Soti.Exercice=R1.Exercice AND Soti.Tiers=R1.Tiers AND Soti.TiersID=R1.TiersID
        LEFT JOIN SIG N5 on N5.id5=agId
			LEFT JOIN SIG N4 on N4.id4=agId
			LEFT JOIN SIG N3 on N3.id3=agId
			LEFT JOIN SIG N2 on N2.id2=agId
			LEFT JOIN SIG N1 on N1.id1=agId
			LEFT JOIN SIG N0 on N0.id0=agId)
        
        , ValeurAjoutee as (
        Select 'SIG' as JournalCode, '' as EcritureDate, '' as compte, '' as compteLib, '' as EcritureLib, 
            replace(to_char(sum(Debit), '000000000000000D99'), '.', ',') AS Debit,
            replace(to_char(sum(Credit), '000000000000000D99'), '.', ',') AS Credit,
            replace(to_char(sum(Balance), '000000000000000D99'), '.', ',') AS Balance,
            '' as PieceRef, '' as EcritureLet, SIG3 as CatResBilan, Societe, Exercice, '' as Tiers, 0 as TiersID, 
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as  article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            '0' AS quantity,
            '0' AS price_unit,
            '0' AS discount,
            '0' AS price_subtotal,
            '' as display_type,
            
            '' as SensBalance, '' as SensSoldeTiers, AnneeMois, 
            replace(to_char(sum(DebitBudget), '000000000000000D99'), '.', ',') AS DebitBudget,
            replace(to_char(sum(CreditBudget), '000000000000000D99'), '.', ',') AS CreditBudget,
            replace(to_char(sum(MontantBudget), '000000000000000D99'), '.', ',') AS MontantBudget, 
            Etat, TypeLigne, 'SIG' as SIG,
            replace(to_char((sum(Balance) * (-1)), '000000000000000D99'), '.', ',') AS MontantM,
            NomBudget,
            '' as CompteClasse,
            '' as CompteType,          
            '' as textefin
        from SuiviDetail 
        where SIG3 = 'Valeur ajoutée'
        group by TypeLigne, AnneeMois, Societe, Exercice, Etat, SIG3, NomBudget
)

        , ResultatExploitation as (
        Select 'SIG' as JournalCode, '' as EcritureDate, '' as compte, '' as compteLib, '' as EcritureLib, 
            replace(to_char(sum(Debit), '000000000000000D99'), '.', ',') AS Debit,
            replace(to_char(sum(Credit), '000000000000000D99'), '.', ',') AS Credit,
            replace(to_char(sum(Balance), '000000000000000D99'), '.', ',') AS Balance,
            '' as PieceRef, '' as EcritureLet, SIG2 as CatResBilan, Societe, Exercice, '' as Tiers, 0 as TiersID, 
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as  article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            '0' AS quantity,
            '0' AS price_unit,
            '0' AS discount,
            '0' AS price_subtotal,
            '' as display_type,
            
            '' as SensBalance, '' as SensSoldeTiers, AnneeMois,
            replace(to_char(sum(DebitBudget), '000000000000000D99'), '.', ',') AS DebitBudget,
            replace(to_char(sum(CreditBudget), '000000000000000D99'), '.', ',') AS CreditBudget,
            replace(to_char(sum(MontantBudget), '000000000000000D99'), '.', ',') AS MontantBudget,
            Etat, TypeLigne, 'SIG' as SIG, 
            replace(to_char((sum(Balance) * (-1)), '000000000000000D99'), '.', ',') AS MontantM,
            NomBudget,
            '' as CompteClasse,
            '' as CompteType,          
            '' as textefin
        from SuiviDetail 
        where SIG2 = 'Résultat d''exploitation'
        group by TypeLigne, AnneeMois, Societe, Exercice, Etat, SIG2, NomBudget
)
        , ResultatCourant as (
        Select 'SIG' as JournalCode, '' as EcritureDate, '' as compte, '' as compteLib, '' as EcritureLib, 
            replace(to_char(sum(Debit), '000000000000000D99'), '.', ',') AS Debit,
            replace(to_char(sum(Credit), '000000000000000D99'), '.', ',') AS Credit,
            replace(to_char(sum(Balance), '000000000000000D99'), '.', ',') AS Balance, 
            '' as PieceRef, '' as EcritureLet, SIG1 as CatResBilan, Societe, Exercice, '' as Tiers, 0 as TiersID, 
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as  article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            '0' AS quantity,
            '0' AS price_unit,
            '0' AS discount,
            '0' AS price_subtotal,
            '' as display_type,
            
            '' as SensBalance, '' as SensSoldeTiers, AnneeMois, 
            replace(to_char(sum(DebitBudget), '000000000000000D99'), '.', ',') AS DebitBudget,
            replace(to_char(sum(CreditBudget), '000000000000000D99'), '.', ',') AS CreditBudget,
            replace(to_char(sum(MontantBudget), '000000000000000D99'), '.', ',') AS MontantBudget, 
            Etat, TypeLigne, 'SIG' as SIG, 
            replace(to_char((sum(Balance) * (-1)), '000000000000000D99'), '.', ',') AS MontantM,
            NomBudget,
            '' as CompteClasse,
            '' as CompteType,          
            '' as textefin
        from SuiviDetail 
        where SIG1 = 'Résultat courant'
        group by TypeLigne, AnneeMois, Societe, Exercice, Etat, SIG1, NomBudget
)

        , Resultat as (
        Select 'SIG' as JournalCode, '' as EcritureDate, '' as compte, '' as compteLib, '' as EcritureLib, 
            replace(to_char(sum(Debit), '000000000000000D99'), '.', ',') AS Debit,
            replace(to_char(sum(Credit), '000000000000000D99'), '.', ',') AS Credit,
            replace(to_char(sum(Balance), '000000000000000D99'), '.', ',') AS Balance,
            '' as PieceRef, '' as EcritureLet, SIG0 as CatResBilan, Societe, Exercice, '' as Tiers, 0 as TiersID, 
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as  article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            '0' AS quantity,
            '0' AS price_unit,
            '0' AS discount,
            '0' AS price_subtotal,
            '' as display_type,
            
            '' as SensBalance, '' as SensSoldeTiers, AnneeMois, 
            replace(to_char(sum(DebitBudget), '000000000000000D99'), '.', ',') AS DebitBudget,
            replace(to_char(sum(CreditBudget), '000000000000000D99'), '.', ',') AS CreditBudget,
            replace(to_char(sum(MontantBudget), '000000000000000D99'), '.', ',') AS MontantBudget,
            Etat, TypeLigne, 'SIG' as SIG, 
            replace(to_char((sum(Balance) * (-1)), '000000000000000D99'), '.', ',') AS MontantM,
            NomBudget,
            '' as CompteClasse,
            '' as CompteType,          
            '' as textefin
        from SuiviDetail 
        where SIG0='Résultat'
        group by TypeLigne, AnneeMois, Societe, Exercice, Etat, SIG0, NomBudget
)

        , Extracompta as (
		Select
            'ANNEXE' as JournalCode,
            to_char(x_date,'DD/MM/YYYY') as EcritureDate,
            '' as CompteNum, 
            '' as compteLib,
            '' as EcritureLib, 
            '0' AS Debit,
            '0' AS Credit,
            replace(to_char(x_balance, '000000000000000D99'), '.', ',') AS Balance,
            '' as PieceRef,
            '' as EcritureLet,
            x_code as CatResBilan,
            S0.name as Societe,
            EF.name as Exercice,
            '' as Tiers,
            0 as TiersID,
            
            0 as codeana,
            '' as affaire,
            0 as codeatelier,
            '' as atelier,
            0 as idclientliv,
            '' as clientliv,
            '' as devisclient,
            0 as id_article,
            '' as default_code,
            0 as id2_article,
            '' as article,
            '' as typearticle,
            0 as idmove,
            '' as ref,
            '' as state,
            '' as type,
            '' as invoice_origin,
            '' as invoice_partner_display_name,
            0 as idmoveline,
            0 as sequence,
            '' as name,
            '0' AS quantity,
            '0' AS price_unit,
            '0' AS discount,
            '0' AS price_subtotal,
            '' as display_type,
            
            '' as SensBalance,
            '' as SensSoldeTiers,
            to_char(x_date,'YYYY-MM') as AnneeMois,
            '0' AS DebitBudget,
            '0' AS CreditBudget,
            '0' AS MontantBudget,
            'Comptabilisé' as Etat,
            'Realise' as TypeLigne,
            '' as SIG,
            replace(to_char(x_balance, '000000000000000D99'), '.', ',') AS MontantM,
            '' as NomBudget,
            '' as CompteClasse,
            '' as CompteType,                
            '' as textefin
        from x_extracompta
		inner join Company S0 on S0.id=x_company_id
		INNER JOIN account_fiscal_year EF on EF.company_id=x_company_id and x_date between EF.date_from and EF.date_to)
        
        
        Select
            JournalCode,
            EcritureDate,
            CompteNum, 
            CompteLib,
            EcritureLib, 
            replace(to_char(Debit, '000000000000000D99'), '.', ',') AS Debit,
            replace(to_char(Credit, '000000000000000D99'), '.', ',') AS Credit,
            replace(to_char(Balance, '000000000000000D99'), '.', ',') AS Balance,
            PieceRef,
            EcritureLet,
            CatResBilan,
            Societe,
            Exercice,
            Tiers,
            TiersID,
            
            codeana,
            affaire,
            codeatelier,
            atelier,
            idclientliv,
            clientliv,
            devisclient,
            id_article,
            default_code,
            id2_article,
             article,
            typearticle,
            idmove,
            ref,
            state,
            type,
            invoice_origin,
            invoice_partner_display_name,
            idmoveline,
            sequence,
            name,
            replace(to_char(quantity, '000000000000000D99'), '.', ',') AS quantity,
            replace(to_char(price_unit, '000000000000000D99'), '.', ',') AS price_unit,
            replace(to_char(discount, '000000000000000D99'), '.', ',') AS discount,
            replace(to_char(price_subtotal, '000000000000000D99'), '.', ',') AS price_subtotal,
            display_type,
            
            SensBalance,
            SensSoldeTiers,
            AnneeMois,
            replace(to_char(DebitBudget, '000000000000000D99'), '.', ',') AS DebitBudget,
            replace(to_char(CreditBudget, '000000000000000D99'), '.', ',') AS CreditBudget,
            replace(to_char(MontantBudget, '000000000000000D99'), '.', ',') AS MontantBudget,
            Etat,
            TypeLigne,
            SIG,
            replace(to_char(MontantM, '000000000000000D99'), '.', ',') AS MontantM,
            NomBudget,
            CompteClasse,
            CompteType,          
            textefin
        from SuiviDetail
        union all
        Select * from ValeurAjoutee
        union all
        Select * from ResultatExploitation
        union all
        Select * from ResultatCourant
        union all
        Select * from Resultat
        union all
		Select * from Extracompta
        
        '''
        
        _logger.info('logLLO_sql_query' + str(sql_query))
        #self._cr.execute(
        #    sql_query, (self.x_date_from, self.x_date_to, company.id,self.x_date_from, self.x_date_to, company.id))
        self._cr.execute(
            sql_query, (self.x_date_from, self.x_date_to,self.x_date_from, self.x_date_to))

        for row in self._cr.fetchall():
            rows_to_write.append(list(row))

        fecvalue = self._csv_write_rows(rows_to_write)
        end_date = fields.Date.to_string(self.x_date_to).replace('-', '')
        start_date = fields.Date.to_string(self.x_date_from).replace('-', '')
        suffix = ''
        if self.x_export_type == "nonofficial":
            suffix = '-Brouillon compris'

        self.write({
            'x_fec_data': base64.encodestring(fecvalue),
            # Filename = <siren>FECYYYYMMDD where YYYMMDD is the closing date
            'x_filename': 'SuiviFinancier_du%s_au_%s%s.txt' % (start_date, end_date, suffix),
            })

        action = {
            'name': 'SuiviFinancier',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=x.suivifinancier&id=" + str(self.id) + "&filename_field=x_filename&field=x_fec_data&download=true&x_filename=" + self.x_filename,
            'target': 'self',
            }
        return action
    

    


    def _csv_write_rows(self, rows, lineterminator=u'\r\n'):
        """
        Write FEC rows into a file
        It seems that Bercy's bureaucracy is not too happy about the
        empty new line at the End Of File.

        @param {list(list)} rows: the list of rows. Each row is a list of strings
        @param {unicode string} [optional] lineterminator: effective line terminator
            Has nothing to do with the csv writer parameter
            The last line written won't be terminated with it

        @return the value of the file
        """
        fecfile = io.BytesIO()
        writer = pycompat.csv_writer(fecfile, delimiter='|', lineterminator='')

        rows_length = len(rows)
        #_logger.info('logLLO_3' + str(rows))
        #_logger.info('logLLO_4' + str(rows_length))
        for i, row in enumerate(rows):
            #_logger.info('logLLO_2' + str(i) + str(row))
            if not i == rows_length - 1:
                row[-1] += lineterminator
            writer.writerow(row)

        fecvalue = fecfile.getvalue()
        fecfile.close()
        return fecvalue
    
    
    