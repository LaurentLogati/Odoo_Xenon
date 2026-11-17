{
    'name': "Analyse variation de stock (comptabilité)",
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': "Achats / ventes / variation de stock estimée à partir des écritures comptables",
    'description': """
Analyse de variation de stock basée sur les écritures comptables
==================================================================

Pour chaque article ayant été acheté ou vendu sur une période, à partir des lignes
d'écriture comptable (account.move.line) des factures/avoirs fournisseurs et clients :

- Quantité achetée (factures fournisseurs, nette des avoirs)
- Quantité vendue (factures clients, nette des avoirs)
- Coût unitaire d'achat sur la période (coût de la fiche article si pas d'achat sur la période)
- Variation de stock calculée = (Quantité achetée - Quantité vendue) * Coût unitaire

Filtrable par période (date de début / date de fin) et par codes analytiques.
""",
    'author': 'Custom',
    'depends': ['account', 'analytic'],
    'data': [
        'security/ir.model.access.csv',
        'reports/account_stock_variation_report.xml',
        'views/account_stock_variation_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
