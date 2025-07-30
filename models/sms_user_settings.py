from odoo import models, fields

class SmsUserSenderNumber(models.Model):
    _name = 'sms.user_sender_number'
    _description = 'Numer nadawcy SMS użytkownika'

    user_id = fields.Many2one(
        'res.users', string='Użytkownik',
        required=True, ondelete='cascade')
    number = fields.Char(
        string='Numer nadawcy',
        required=True)

class ResUsers(models.Model):
    _inherit = 'res.users'

    sender_number_ids = fields.One2many(
        'sms.user_sender_number', 'user_id',
        string='Numery nadawcy')
    default_sender_number_id = fields.Many2one(
        'sms.user_sender_number',
        string='Domyślny numer nadawcy',
        help='Numer, z którego będzie domyślnie wysyłane SMS')
    stats_email = fields.Char(
        string='E-mail do wysyłki statystyk',
        help='Statystyki SMS będą wysyłane na ten adres')

    sms_api_endpoint = fields.Char(
        string='Sms api endpoint',
        help='Sms api endpoint')

    sms_api_user = fields.Char(
        string='Sms api user',
        help='Sms api user')

    sms_api_password = fields.Char(
        string='Sms api password',
        help='Sms api password')

    # Dni tygodnia
    send_on_monday    = fields.Boolean(string='Poniedziałek', default=True)
    send_on_tuesday   = fields.Boolean(string='Wtorek',     default=True)
    send_on_wednesday = fields.Boolean(string='Środa',      default=True)
    send_on_thursday  = fields.Boolean(string='Czwartek',   default=True)
    send_on_friday    = fields.Boolean(string='Piątek',     default=True)
    send_on_saturday  = fields.Boolean(string='Sobota',     default=False)
    send_on_sunday    = fields.Boolean(string='Niedziela',  default=False)

    # Godziny (widget float_time)
    hours_from = fields.Float(
        string='Godzina od',
        default=8.0,
        help='Pierwsza godzina, w której dozwolone jest wysyłanie SMS',
        digits=(2, 2))
    hours_to   = fields.Float(
        string='Godzina do',
        default=20.0,
        help='Ostatnia godzina, w której dozwolone jest wysyłanie SMS',
        digits=(2, 2))
