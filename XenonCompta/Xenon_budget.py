from odoo import models, fields, api

  
    
class XenonBudget(models.Model):
    _name='x_budget'
    _description="Budget"
    
    x_libelle=fields.Char(string='Libelle', required=True)
    x_company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.company)
    x_currency_id = fields.Many2one("res.currency", related='x_company_id.currency_id', string="Currency", readonly=True, required=True)
    x_entrepot=fields.Char(string='Entrepot')
    x_datedebut=fields.Date(string='Date de debut',required=True)
    x_datefin=fields.Date(string='Date de fin',required=True)
    x_exercice=fields.Char(string='Exercice fiscal')
    x_actif=fields.Boolean()
    x_statut=fields.Selection([
       ('draft', 'Brouillon'),
        ('cancel', 'Annulé'),
        ('validate', 'Validé'),
        ], string='Statut', readonly=True, copy=False, index=True, tracking=3, default='draft')
    x_priorite=fields.Integer()
    x_prevision=fields.Selection([
       ('bas', 'Basse'),
        ('moy', 'Moyenne'),
        ('hau', 'Haute'),
        ], string='Prevision', readonly=True, copy=True, index=True)
    x_analytique=fields.Many2one('account.analytic.account')
    x_projet=fields.Char(string='Projet')
    x_contact=fields.Char(string='Contact')
    
    
    x_detail_id=fields.One2many('x_budget.detail','x_liste_ids', string="detail")
    

    
class XenonCalculPrixDetail(models.Model):
    _name='x_budget.detail'
    _description="Détail du budget"
    
    x_liste_ids=fields.Many2one('x_budget',string="Détail", ondelete='cascade')
    
    x_company_id = fields.Many2one(related='x_liste_ids.x_company_id', store=True, readonly=True)
    x_company_currency_id = fields.Many2one(related='x_company_id.currency_id', string='Company Currency',
        readonly=True, store=True,
        help='Utility field to express amount currency')
    x_compte=fields.Many2one('account.account')
    x_montant_1=fields.Monetary(string='Montant1', default=0.0, currency_field='x_company_currency_id')
    x_montant_2=fields.Monetary(string='Montant2', default=0.0, currency_field='x_company_currency_id')
    x_montant_3=fields.Monetary(string='Montant3', default=0.0, currency_field='x_company_currency_id')
    x_montant_4=fields.Monetary(string='Montant4', default=0.0, currency_field='x_company_currency_id')
    x_montant_5=fields.Monetary(string='Montant5', default=0.0, currency_field='x_company_currency_id')
    x_montant_6=fields.Monetary(string='Montant6', default=0.0, currency_field='x_company_currency_id')
    x_montant_7=fields.Monetary(string='Montant7', default=0.0, currency_field='x_company_currency_id')
    x_montant_8=fields.Monetary(string='Montant8', default=0.0, currency_field='x_company_currency_id')
    x_montant_9=fields.Monetary(string='Montant9', default=0.0, currency_field='x_company_currency_id')
    x_montant_10=fields.Monetary(string='Montant10', default=0.0, currency_field='x_company_currency_id')
    x_montant_11=fields.Monetary(string='Montant11', default=0.0, currency_field='x_company_currency_id')
    x_montant_12=fields.Monetary(string='Montant12', default=0.0, currency_field='x_company_currency_id')
    x_montant_13=fields.Monetary(string='Montant13', default=0.0, currency_field='x_company_currency_id')
    x_montant_14=fields.Monetary(string='Montant14', default=0.0, currency_field='x_company_currency_id')
    x_montant_15=fields.Monetary(string='Montant15', default=0.0, currency_field='x_company_currency_id')
    x_montant_16=fields.Monetary(string='Montant16', default=0.0, currency_field='x_company_currency_id')
    x_montant_17=fields.Monetary(string='Montant17', default=0.0, currency_field='x_company_currency_id')
    x_montant_18=fields.Monetary(string='Montant18', default=0.0, currency_field='x_company_currency_id')
    x_montant_19=fields.Monetary(string='Montant19', default=0.0, currency_field='x_company_currency_id')
    x_montant_20=fields.Monetary(string='Montant20', default=0.0, currency_field='x_company_currency_id')
    x_montant_21=fields.Monetary(string='Montant21', default=0.0, currency_field='x_company_currency_id')
    x_montant_22=fields.Monetary(string='Montant22', default=0.0, currency_field='x_company_currency_id')
    x_montant_23=fields.Monetary(string='Montant23', default=0.0, currency_field='x_company_currency_id')
    x_montant_24=fields.Monetary(string='Montant24', default=0.0, currency_field='x_company_currency_id')
    x_entrepot=fields.Char(string='Entrepot')    
    x_analytique=fields.Many2one('account.analytic.account')
    x_projet=fields.Char(string='Projet')
    x_contact=fields.Char(string='Contact')
    
    
        
