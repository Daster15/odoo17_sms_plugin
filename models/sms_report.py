from odoo import models, fields, api

def _compute_stats(self):
    for wiz in self:
        domain = [
            ('date_scheduled', '>=', wiz.date_from),
            ('date_scheduled', '<=', wiz.date_to)
        ]
        msgs = self.env['sms.message'].search(domain)
        wiz.total = len(msgs)
        wiz.sent = len(msgs.filtered(lambda m: m.state=='sent'))
        wiz.failed = len(msgs.filtered(lambda m: m.state=='failed'))

class SmsReport(models.TransientModel):
    _name = 'sms.report.wizard'
    _description = 'SMS Report Wizard'

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    total = fields.Integer(string='Total Messages', compute=_compute_stats)
    sent = fields.Integer(string='Sent', compute=_compute_stats)
    failed = fields.Integer(string='Failed', compute=_compute_stats)

    def action_print_report(self):
        return self.env.ref('odoo17_sms_plugin.action_report_sms_summary').report_action(self)
