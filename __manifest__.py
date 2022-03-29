# -*- coding: utf-8 -*-
{
    'name': 'Brother Inv Rounding Custom',
    'version': '1.0',
    'summary': 'Invoice',
    'author':
        'ENZAPPS',
    'sequence': 20,
    'description': """Brother Inv Rounding Custom""",
    'category': '',
    'website': 'https://enzapps.com',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts','account','enz_brothers_dec','enz_multi_updations','enz_mc_owner'],
    'images': ['static/description/logo.png'],
    'data': [
        'report/einv_invoice_report.xml',
        'report/tax_invoice_report.xml'
        # 'security/ir.model.access.csv',
    ],
    'demo': [],
    'qweb': [],
    'installable': True,
    'application': True,
    'auto_install': False,

}
