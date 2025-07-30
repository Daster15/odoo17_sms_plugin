{
    'name': 'SMS Platform',
    'version': '1.4',
    'author': 'Your Company',
    'category': 'Marketing',
    'summary': 'SMS via API with templates, char count, polling status',
    'depends': ['base', 'crm', 'mail','portal'],
    'data': [
        'security/ir.model.access.csv',
        'views/sms_views.xml',           # definiuje menu_sms_root
        'views/sms_template_views.xml',  # teraz może odwołać się do menu_sms_root
        'views/sms_campaign_views.xml',
        'views/sms_conversation_views.xml',
        'views/sms_report_views.xml',
        'reports/sms_report_templates.xml',
        'reports/sms_report_actions.xml',
        'views/sms_campaign_portal_templates.xml',
        'data/cron_jobs.xml',
        'views/res_users_views.xml',
        'data/email_template_campaign_report.xml',

    ],
    'demo': [
      #  'data/sms_conversation_demo.xml',
      #  'data/sms_campanings.xml',
       # 'data/sms_demo_data.xml',
    ],
    #'qweb': [
    #     'odoo17_sms_plugin/static/src/xml/contacts_table.xml',
    #],
    'assets': {
        # Ładujemy nasz szablon OWL w QWeb, żeby <t t-owl="…"/> go odnalazł
       # 'web.assets_qweb': [
       #   'odoo17_sms_plugin/static/src/xml/contacts_table.xml',

        # Ładujemy kod JS przy renderze strony portalowej
        'web.assets_frontend': [
            'odoo17_sms_plugin/static/src/js/contacts_table.js',
            'odoo17_sms_plugin/static/src/xml/contacts_table.xml',
            'odoo17_sms_plugin/static/src/js/portal_sms_charcount.js',
        ],
    },
    'installable': True,
    'application': True,
}
