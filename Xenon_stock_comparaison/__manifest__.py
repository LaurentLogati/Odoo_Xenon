{
    'name': "Comparaison de valorisation de stock entre 2 dates",
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': "Comparer quantités, coûts et valorisation du stock entre deux dates",
    'description': """
Assistant de comparaison de stock entre deux dates
====================================================

Pour chaque article stockable, calcule :
- Quantité, coût unitaire et valorisation à la date 1
- Quantité réceptionnée / livrée / ajustée (inventaire) entre les 2 dates
- Quantité théorique reconstituée
- Quantité, coût unitaire et valorisation à la date 2
- Écart entre quantité théorique et quantité réelle à la date 2

S'appuie sur stock.valuation.layer (historique de valorisation), donc ne fonctionne
que pour les produits en coût réel/FIFO/AVCO (valorisation automatique).
""",
    'author': 'Custom',
    'depends': ['stock_account'],
    'data': [
        'security/ir.model.access.csv',
        'reports/stock_valuation_comparison_report.xml',
        'views/stock_valuation_comparison_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
