from odoo import models, fields, api, _
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"


    def action_cancel_create(self):
            if self.invoice_id:
                self.invoice_id.sudo().write({'state':'cancel'})

            ledger_invoices = self.env['partner.ledger.customer'].sudo().search([('invoice_id','=',self.invoice_id.id),('company_id','=',self.invoice_id.company_id.id)])
            if ledger_invoices:
                for each_ledger in ledger_invoices:
                    each_ledger.unlink()

            # override the context to get rid of the default filtering
            product_list = []
            for line in self.sales_return_lines:
                account_id = self.env['account.account'].search(
                    [('company_id', '=', self.invoice_id.company_id.id), ('name', '=', 'Local Sales')])

                line_dict = (0,0,{
                    'name': line.sudo().product_id.name,
                    'account_id': account_id.id,
                    'price_unit': line.price_unit,
                    'quantity': line.product_uom_qty,
                    # 'discount': 0.0,
                    # 'uom_id': line.product_id.uom_id.id,
                    'product_id': line.sudo().product_id.id,
                    'tax_ids': [(6, 0, line.sudo().tax_ids.ids)]})
                product_list.append(line_dict)

            new_inv = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.partner_id.id,
                'currency_id': self.invoice_id.currency_id.id,
                'company_id': self.invoice_id.company_id.id,
                'branch_id': self.branch_id.id,
                'est_line_id': self.sales_return_lines[0].est_line_id.id,
                'invoice_line_ids':product_list,
                # 'origin': self.name
            })
            new_inv.write({'estimate_id': self.invoice_id.estimate_id.id})
            new_inv.remarks = self.invoice_id.remarks
            new_inv.b2b_company_name = self.partner_id.b2b_company_name
            new_inv.site = self.partner_id.site
            new_inv.complete_address = self.complete_address
            new_inv.vehicle = self.vehicle
            if not self.invoice_id.balance_invoice_qty:
                self.invoice_id.balance_invoice_qty = sum(self.invoice_id.mapped('invoice_line_ids').filtered(lambda a:a.is_rounding_line_enz != True).mapped('quantity')) - sum(new_inv.mapped('invoice_line_ids').filtered(lambda a:a.is_rounding_line_enz != True).mapped('quantity'))
            else:
                self.invoice_id.balance_invoice_qty = self.invoice_id.balance_invoice_qty-sum(new_inv.mapped('invoice_line_ids').filtered(lambda a:a.is_rounding_line_enz != True).mapped('quantity'))
            # if new_inv.amount_total > round(new_inv.amount_total):
            #     rounding_line = self.env['account.move.line'].create({
            #         'name': 'Rounding 0.05',
            #         'move_id': new_inv.id,
            #         # 'account_id': self.env['account.cash.rounding'].search(
            #         #     [('name', '=', 'Rounding 0.05')]).profit_account_id.id,
            #         'account_id': self.env['account.cash.rounding'].search(
            #             [('name', '=', 'Rounding 0.05')]).sudo().loss_account_id.id,
            #         'price_unit': -(new_inv.amount_total - round(new_inv.amount_total)),
            #         'quantity': 1,
            #         'is_rounding_line': True,
            #         'sequence': 9999  # always last line
            #     })
            # else:
            #     if new_inv.amount_total < round(new_inv.amount_total):
            #         rounding_line = self.env['account.move.line'].create({
            #             'name': 'Rounding 0.05 Up',
            #             'move_id': new_inv.id,
            #             'account_id': self.env['account.cash.rounding'].search(
            #                 [('name', '=', 'Rounding up 0.05')]).sudo().profit_account_id.id,
            #             'price_unit': round(new_inv.amount_total) - new_inv.amount_total,
            #             'quantity': 1,
            #             'is_rounding_line': True,
            #             'sequence': 9999  # always last line
            #         })

            # new_inv.action_invoice_open()
            new_inv.action_post()
            self.new_invoices = new_inv

            for inv_line in new_inv.invoice_line_ids.filtered(lambda a:a.is_rounding_line_enz != True):

                invoices = self.env['account.move'].sudo().search(
                    [('partner_id', '=', new_inv.partner_id.id), ('company_id', '=', new_inv.company_id.id),
                     ('state', '!=', 'paid')])
                if invoices.mapped('amount_residual'):
                    balance_amount = sum(invoices.mapped('amount_residual'))
                else:
                    balance_amount = sum(invoices.mapped('amount_total'))
                balance_amount += self.env['partner.ledger.customer'].sudo().search(
                    [('partner_id', '=', new_inv.partner_id.id), ('description', '=', 'Opening Balance')]).balance
                Previous_led = self.env['partner.ledger.customer'].sudo().search(
                    [('company_id', '=', new_inv.company_id.id), ('partner_id', '=', new_inv.partner_id.id)])
                if Previous_led:
                    # balance_amount = Previous_led[-1].balance + inv_line.price_subtotal_signed + new_inv.amount_tax
                    balance_amount = Previous_led[-1].balance + inv_line.price_subtotal+ new_inv.amount_tax

                # bal = sum(
                #     self.env['account.move.line'].search([('journal_id', '=', self.account_journal.id)]).mapped('debit'))

                self.env['partner.ledger.customer'].sudo().create({
                    'date': datetime.today().date(),
                    'invoice_id': new_inv.id,
                    'description': inv_line.product_id.name,
                    'partner_id': new_inv.partner_id.id,
                    'product_id': inv_line.product_id.id,
                    'company_id': new_inv.company_id.id,
                    'price_units': new_inv.inv_mc_qty,
                    'uom': inv_line.product_id.uom_id.id,
                    'rate': inv_line.price_unit,
                    'estimate_id': self.invoice_id.estimate_id.id,
                    'account_journal': new_inv.journal_id.id,
                    'account_move': new_inv.id,
                    # 'credit': inv.amount_total_signed,
                    # 'debit': inv_line.price_subtotal_signed + new_inv.amount_tax,
                    'debit': inv_line.price_subtotal + new_inv.amount_tax,
                    # 'balance': 0,
                    'executive_area': self.invoice_id.estimate_id.executive_areas.id or False,
                    'area': self.invoice_id.estimate_id.area.id or False,
                    'vehicle_id': self.invoice_id.estimate_id.estimate_ids[0].vahicle.id,
                    'balance': balance_amount,
                })
                # self.env['owner.application'].create({
                #     'create_date': self.c_date,
                #     'partner_id': new_inv.partner_id.id,
                #     'product_id': line.product_id.id,
                #     'quantity': new_inv.inv_mc_qty,
                #     'company_id': new_inv.company_id.id,
                #     'type': self.estimtype,
                #     'area': self.invoice_id.estimate_id.area.id or False,
                #     'outstanding_amount': balance_amount,
                #     'sales_executive': self.user_id.partner_id.id
                # })
            self.write({'state':'done'})



    def _compute_inv_mc_qty(self):
        for each_inv in self:
            each_inv.inv_mc_qty = sum(
                each_inv.invoice_line_ids.filtered(lambda a: a.is_rounding_line_enz != True).mapped('quantity'))

class SaleEstimate(models.Model):
    _inherit = 'sale.estimate'

    def create_main_partner(self, inv):
        for line in inv.invoice_line_ids.filtered(lambda a: a.is_rounding_line_enz != True):
            invoices = self.env['account.move'].search(
                [('partner_id', '=', inv.partner_id.id), ('company_id', '=', inv.company_id.id),
                 ('state', '!=', 'paid')])
            if invoices.mapped('amount_residual'):
                balance_amount = sum(invoices.mapped('amount_residual'))
            else:
                balance_amount = sum(invoices.mapped('amount_total'))
            balance_amount += self.env['partner.ledger.customer'].search(
                [('partner_id', '=', inv.partner_id.id), ('description', '=', 'Opening Balance')]).balance
            Previous_led = self.env['partner.ledger.customer'].search(
                [('company_id', '=', inv.company_id.id), ('partner_id', '=', inv.partner_id.id)])
            if Previous_led:
                balance_amount = Previous_led[-1].balance + line.price_subtotal

            else:
                balance_amount = balance_amount + line.price_subtotal - inv.amount_total

            # bal = sum(
            #     self.env['account.move.line'].search([('journal_id', '=', self.account_journal.id)]).mapped('debit'))

            self.env['partner.ledger.customer'].sudo().create({
                'date': self.c_date,
                'invoice_id': inv.id,
                'description': line.product_id.name,
                'partner_id': inv.partner_id.id,
                'product_id': line.product_id.id,
                'company_id': inv.company_id.id,
                # 'price_units': inv.inv_mc_qty,
                'price_units': line.quantity,
                'uom': line.product_id.uom_id.id,
                'rate': line.price_unit,
                'estimate_id': self.id,
                'account_journal': inv.journal_id.id,
                # 'account_move': inv.move_id.id,
                'account_move': inv.id,
                # 'credit': inv.amount_total_signed,
                'debit': line.price_subtotal,
                # 'balance': 0,
                'executive_area': self.executive_areas.id or False,
                'area': self.area.id or False,
                'vehicle_id': self.estimate_ids[0].vahicle.id,
                'balance': balance_amount,
            })
            self.env['owner.application'].create({
                'create_date': self.c_date,
                'partner_id': inv.partner_id.id,
                'product_id': line.product_id.id,
                'quantity': inv.inv_mc_qty,
                'company_id': inv.company_id.id,
                'type': self.type,
                'area': self.area.id or False,
                'outstanding_amount': balance_amount,
                'sales_executive': self.user_id.partner_id.id
            })

    def action_partner_ledger(self):
            for inv in self.invoice_ids:
                if inv.company_id.id == 1:
                    self.create_main_partner(inv)
                else:
                    balance_amount = 0
                    for line in inv.invoice_line_ids.filtered(lambda a: a.is_rounding_line_enz != True):
                        invoices = self.env['account.move'].search(
                            [('partner_id', '=', inv.partner_id.id), ('company_id', '=', inv.company_id.id),
                             ('state', '!=', 'paid')])
                        if invoices.mapped('amount_residual'):
                            balance_amount = sum(invoices.mapped('amount_residual'))
                        else:
                            balance_amount = sum(invoices.mapped('amount_total'))
                        balance_amount += self.env['partner.ledger.customer'].search(
                            [('partner_id', '=', inv.partner_id.id), ('description', '=', 'Opening Balance')]).balance
                        Previous_led = self.env['partner.ledger.customer'].search(
                            [('company_id', '=', inv.company_id.id), ('partner_id', '=', inv.partner_id.id)])
                        if Previous_led:
                            # balance_amount = Previous_led[-1].balance + line.price_subtotal_signed + inv.amount_tax
                            balance_amount = Previous_led[-1].balance + line.price_subtotal + inv.amount_tax

                        # bal = sum(
                        #     self.env['account.move.line'].search([('journal_id', '=', self.account_journal.id)]).mapped('debit'))

                        self.env['partner.ledger.customer'].sudo().create({
                            'date': self.c_date,
                            'invoice_id': inv.id,
                            'description': line.product_id.name,
                            'partner_id': inv.partner_id.id,
                            'product_id': line.product_id.id,
                            'company_id': inv.company_id.id,
                            'price_units': inv.inv_mc_qty,
                            'uom': line.product_id.uom_id.id,
                            'rate': line.price_unit,
                            'estimate_id': self.id,
                            'account_journal': inv.journal_id.id,
                            # 'account_move': inv.move_id.id,
                            'account_move': inv.id,
                            # 'credit': inv.amount_total_signed,
                            # 'debit': line.price_subtotal_signed + inv.amount_tax,
                            'debit': line.price_subtotal + inv.amount_tax,
                            # 'balance': 0,
                            'executive_area': self.executive_areas.id or False,
                            'area': self.area.id or False,
                            'vehicle_id': self.estimate_ids[0].vahicle.id,
                            'balance': balance_amount,
                        })
                        self.env['owner.application'].create({
                            'create_date': self.c_date,
                            'partner_id': inv.partner_id.id,
                            'product_id': line.product_id.id,
                            'quantity': inv.inv_mc_qty,
                            'company_id': inv.company_id.id,
                            'type': self.type,
                            'area': self.area.id or False,
                            'outstanding_amount': balance_amount,
                            'sales_executive': self.user_id.partner_id.id
                        })


    def action_approve(self):
        # get_mac()
        # if self.est_order_id:

        if self.partner_id:
            list = []
            expense = 0
            inb = self.env['account.move']
            ###################################3 for testing############################################3

            self.total_sales_create()
            #########################################################################################33
            est = self.env['estimate.analysis']
            order = self.env['sale.order']
            for line in self.estimate_ids:
                sum(line.sub_customers.mapped('quantity'))
                if line.company_ids.id != 1:
                    # line.sub_customers
                    if not line.company_ids:
                        raise UserError('Before Approve the Estimate  Mention Company Name in Products Lines')
                    # if line.vahicle_expense:
                    #     expense += line.vahicle_expense
                    if line.exp_inv_price:
                        if line.company_ids != line.vahicle.company_id:

                        ##################################################################
                            self.env['expense.balance.payment'].create({
                                'est_date':self.create_date,
                                'estimate_id':self.id,
                                'est_from_company':line.company_ids.id,
                                'partner_id':line.company_ids.partner_id.id,
                                # 'est_to_company':line.company_ids.id,
                                'est_to_company':line.vahicle.company_id.id,
                                'vahicle':line.vahicle.id,
                                'company_id': line.company_ids.id,
                                'vahicle_exp_amount':line.vahicle_expense,
                                'excluded_value':line.vahicle_basic_expense,
                                'vahicle_inv_amount':line.exp_inv_price,
                                'balance':line.exp_inv_price,
                                'exp_diff':line.vahicle_expense-line.exp_inv_price,




                            })

                            self.env['expenses.balance.payment'].create({
                                'estimate': self.id,
                                'estimate_amount': line.vahicle_expense,
                                # 'estimate_amount': line.vahicle_basic_expense,
                                'date': self.create_date,
                                'est_from_company': line.company_ids.id,
                                'paid': 0,
                                'est_to_company': line.vahicle.company_id.id,
                                'company_id': self.company_id.id,
                                # 'get_balance':  line.vahicle_expense-line.exp_inv_price,
                                'get_balance':  line.exp_inv_price,
                                'excluded_value':  line.vahicle_basic_expense,
                                'complete_invoiced':line.exp_inv_price,
                                # 'balance': line.vahicle_expense-line.exp_inv_price,
                                'balance': line.exp_inv_price,
                                # 'balance': line.vahicle_basic_expense-line.exp_inv_price,
                                'partner_id':line.company_ids.partner_id.id
                                })

                        else:
                        # expense += line.exp_inv_price
                            expense = line.exp_inv_price
                            if expense:
                                product = self.env['product.product'].search([('name', '=', 'Expenses')])
                                hr = self.env['hr.expense'].sudo().create({
                                    'product_id': product.id,
                                    'quantity': 1,
                                    'unit_amount': expense,
                                    'name': 'Vahicle Expenses',
                                    'estimate_ref': self.name,
                                    'company_id': line.company_ids.id

                                })
                                # partner = self.partner
                                if line.company_ids != line.vahicle.company_id:

                                    order_req = self.env['sale.request'].create({
                                        'partner_id': self.company_id.partner_id.id,
                                        'to_company_id':line.vahicle.company_id.id,
                                        'req_company_id':line.company_ids.id,
                                        'order_id':self.id,
                                        'sale_date': self.sale_date,
                                    })
                                    if order_req:

                                        # order.warehouse_id = self.env['stock.warehouse'].search([('company_id','=',line.vahicle.company_id.id)]).id
                                        product = self.env['product.product'].search([('name', '=', 'Vahicle Rent')])
                                        if product:
                                            product = product.id
                                        sale_line = self.env['sale.request.lines'].create({
                                            'taluk':line.taluks.id or line.dippo_id.taluks.id,
                                            'dippo_id':line.dippo_id.id,
                                                                                        'product_id': product,
                                                                                        'product_uom_qty':1,
                                                                                         'vahicle':line.vahicle.id,
                                                                                        'exp_inv_price': line.exp_inv_price,
                                                                                        'request_id': order_req.id})
                                    # order.company_id = line.vahicle.company_id.id

                    # if line.company_ids == self.company_id:
                    if line.sub_customers:
                        for sub_cus in line.sub_customers:
                            # ratio = int(self.vat[-2:])
                            # if ratio:
                            #     self.vat = self.vat[:-2]
                            # warehouse = self.env['stock.warehouse'].search([('company_id', 'in', line.company_ids.id)])

                            # qty = round(line.product_uom_qty * ratio/100)
                            if sub_cus.partner.partner:
                                partner = sub_cus.partner.partner
                            else:
                                partner = sub_cus.partner.sub_part
                            order = self.env['sale.order'].sudo().create({
                                # 'partner_id': self.partner_id.id,
                                'partner_id': partner.id,
                                'partner_invoice_id': partner.id,
                                'partner_shipping_id': partner.id,
                                'pricelist_id': self.env.ref('product.list0').id,
                                'picking_policy': 'direct',
                                'company_id': line.company_ids.id,
                                'order_id': self.id,
                                'user_id': self.user_id.id,
                                # 'warehouse_id': line.warehouse.id,
                                'warehouse_id': self.env['stock.warehouse'].sudo().search([('company_id','=',line.company_ids.id)]).id,
                                # 'warehouse_id': 1,
                            })

                            if order:
                                if partner.b_to_b == True:
                                    b= self.env['sale.btob'].create({'test_bb':'B2B'})
                                    # order.name = 'B2B' + '/' + order.name
                                    order.name = b.name
                                else:
                                    c = self.env['sale.btoc'].create({'test_bc':'B2c'})
                                    order.name = c.name


                                    # order.name = 'B2C' + '/' + order.name
                            value=0
                            if sub_cus.basic_value:
                                value = sub_cus.basic_value
                            else:
                                value = sub_cus.amount
                            su_taxes = self.env['account.tax']
                            for each_tax in line.tax_ids:
                                su_taxes += self.env['account.tax'].search([('name','=',each_tax.name),('type_tax_use', '=', 'sale'),('company_id','=',order.company_id.id)])


                            sale_line = self.env['sale.order.line'].sudo().create({'name': line.product_id.name,
                                                                            'product_id': line.product_id.id,
                                                                            # 'product_uom_qty': line.product_uom_qty/2,
                                                                            # 'product_uom_qty': qty,
                                                                            'product_uom_qty': sub_cus.quantity,
                                                                            'product_uom': line.product_uom.id,
                                                                            'including_price':sub_cus.basic_value,
                                                                            # 'price_uint': line.price_total,
                                                                            # 'price_uint': line.price_unit,
                                                                            # 'price_unit': sub_cus.amount,
                                                                            # 'price_unit': sub_cus.basic_value,
                                                                            'price_unit': value,
                                                                            'customer_lead': line.product_id.sale_delay,
                                                                            # 'tax_id':[(6,0,sub_cus.tax_ids.ids)],
                                                                            'tax_id':[(6,0,su_taxes.ids)],
                                                                            'taluk':line.taluks.id or line.dippo_id.taluks.id,
                                                                            'order_id': order.id})
                            # sale_line.price_unit = line.price_total / 2
                            # sale_line.price_unit = sub_cus.basic_value
                            sale_line.price_unit = value
                            # sale_line.price_unit = line.price_unit
                            # lines = (0, 0, {'name': line.product_id.name,
                            #                 'product_id': line.product_id.id,
                            #                 'product_uom_qty': line.price_total/2,
                            #                 'product_uom': line.product_uom.id,
                            #                 'customer_lead': line.product_id.sale_delay})
                            # list.append(lines)

                            order.sudo().action_confirm()
                            # for pickings in order.picking_ids:
                            #     pickings.action_assign()
                            #     pickings.button_validate()
                            #     m = pickings.button_validate()
                            #     immideate = self.env['stock.immediate.transfer'].browse(m['res_id'])
                            #     immideate.process()

                            # for pickings in order.picking_ids:
                            #     pickings.action_assign()
                            #     pickings.button_validate()
                            order.ref = order.name[-4:]
                            if self.sale_date:
                                order.confirmation_date = self.sale_date
                            # self.create_invoices(order)
                            # invoice = order.sudo().action_invoice_create()
                            invoice = order.sudo()._create_invoices()
                            inb = invoice
                            # inb = self.env['account.move'].sudo().browse(invoice[0])
                            # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name','=','Rounding 0.05')])
                            # inb.account_id = self.env['account.account'].sudo().search([('name','=','Debtors'),('company_id','=',inb.company_id.id)])
                            # inb.write({'tax_id': [(6, 0, line.tax_ids.ids)]})

                            # inb.write({'tax_id': [(6, 0, line.tax_ids.ids)]})
                            acc_taxes = self.env['account.tax']
                            for each_tax in line.tax_ids:
                                acc_taxes += self.env['account.tax'].search(
                                    [('name', '=', each_tax.name), ('type_tax_use', '=', 'sale'),
                                     ('company_id', '=', inb.company_id.id)])

                            # inb.write({'tax_id': [(6, 0, line.tax_ids.ids)]})
                            # inb.write({'tax_id': [(6, 0, acc_taxes.ids)]})
                            inb.write({'estimate_id':self.id})
                            inb.write({'est_line_id':line.id})
                            inb.write({'branch_id':line.branch_id.id})
                            inb.remarks = self.remarks
                            inb.complete_address = sub_cus.complete_address
                            for pickings in order.picking_ids:
                                if pickings.company_id == inb.company_id:
                                    # inb.picking_id = pickings
                                    pickings.inv_id = inb

                            inb.b2b_company_name = inb.partner_id.b2b_company_name
                            inb.site = inb.partner_id.site
                            for v_line in inb.invoice_line_ids:
                                if v_line.product_id == line.product_id:
                                    v_line.taluk =line.taluks.id or line.dippo_id.taluks.id
                                    inb.vehicle = line.vahicle_char.vehi_reg
                                    # for line_vehicle in self.estimate_ids:
                                    inb.vehicle_number = line.vahicle.license_plate

                                    v_line.hsn_code = v_line.product_id.l10n_in_hsn_code
                                    v_line.including_price =sub_cus.amount
                            # invoice.payment_move_line_ids
                            # if inb.amount_total > round(inb.amount_total):
                            #    # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name','=','Rounding 0.05')])
                            #    # inb._onchange_cash_rounding()
                            #    # rounding_amount = inb.cash_rounding_id.compute_difference(inb.currency_id,
                            #    #                                                            inb.amount_total)
                            #    profit_acc_name = self.env['account.account'].sudo().search([('company_id','=',inb.company_id.id),('name','=',self.env['account.cash.rounding'].search(
                            #            [('name', '=', 'Rounding 0.05')]).profit_account_id.name),('company_id','=',inb.company_id.id)])
                            #    round_acc = self.env['account.account'].sudo().search([('name','=',profit_acc_name.name),('company_id','=',inb.company_id.id)])
                            #
                            #    rounding_line = self.env['account.move.line'].sudo().create({
                            #        'name': 'Rounding 0.05',
                            #        'move_id': inb.id,
                            #        'account_id': round_acc.id,
                            #        # 'loss_account_id': self.env['account.cash.rounding'].search(
                            #        #     [('name', '=', 'Rounding 0.05')]).loss_account_id.id,
                            #        # 'account_id': self.env['account.cash.rounding'].search([('name','=','Rounding 0.05')]).account_id.id,
                            #        'price_unit': -(inb.amount_total-round(inb.amount_total)),
                            #        'quantity': 1,
                            #        'is_rounding_line': True,
                            #        'sequence': 9999  # always last line
                            #    })
                            # else:
                            #    if inb.amount_total < round(inb.amount_total):
                            #        # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name', '=', 'Rounding 0.05')])
                            #        # # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name', '=', 'Rounding 0.05')])
                            #        # # inb._onchange_cash_rounding()
                            #        # rounding_amount = inb.cash_rounding_id.compute_difference(inb.currency_id,
                            #        #                                                           inb.amount_total)
                            #        profit_acc_name = self.env['account.account'].sudo().search(
                            #            [('company_id','=',inb.company_id.id),('name', '=', self.env['account.cash.rounding'].search(
                            #                [('name', '=', 'Rounding 0.05')]).profit_account_id.name)])
                            #        round_acc = self.env['account.account'].search(
                            #            [('name', '=', profit_acc_name.name),
                            #             ('company_id', '=', inb.company_id.id)])
                            #
                            #        rounding_line = self.env['account.move.line'].sudo().create({
                            #            'name': 'Rounding 0.05 Up',
                            #            'move_id': inb.id,
                            #            # 'account_id': self.env['account.cash.rounding'].search(
                            #            #     [('name', '=', 'Rounding up 0.05')]).account_id.id,
                            #            'account_id': round_acc.id,
                            #            # 'loss_account_id': self.env['account.cash.rounding'].search(
                            #            #     [('name', '=', 'Rounding up 0.05')]).loss_account_id.id,
                            #            'price_unit': round(inb.amount_total)-inb.amount_total,
                            #            'quantity': 1,
                            #            'is_rounding_line': True,
                            #            'sequence': 9999  # always last line
                            #        })

                               # To be able to call this onchange manually from the tests,
                               # ensure the inverse field is updated on account.move.
                               # inb.invoice_line_ids += rounding_line

                            inb.sudo().action_post()
                            if self.sale_date:
                                inb.invoice_date = self.sale_date
                            if order.ref:
                                inb.ref = order.ref


                            self.env['estimate.balance'].create({'estimate': self.id,
                                                                 'estimate_line': line.id,
                                                                 'product_id': line.product_id.id,
                                                                 'quantity': line.product_uom_qty,
                                                                 'partner_id': self.partner_id.id,
                                                                 'date': datetime.today().date(),
                                                                 'balance': line.price_unit - line.inv_price
                                                                 })
                            # partner = sub_cus.partner.partner
                            if sub_cus.partner.partner:
                                partner = sub_cus.partner.partner
                            else:
                                partner = sub_cus.partner.sub_part

                            est = self.env['estimate.analysis'].create({'estimate': self.id,
                                                                        'company_id': line.company_ids.id,
                                                                        'estimate_line': line.id,
                                                                        'product_id': line.product_id.id,
                                                                        'quantity': line.product_uom_qty,
                                                                        'partner_id': self.partner_id.id,
                                                                        'sub_partner_id': partner.id,
                                                                        'date': datetime.today().date(),
                                                                        'b_to_b': partner.b_to_b,
                                                                        # 'estimate_amount': line.price_total,
                                                                        # 'amount': line.inv_price,
                                                                        'amount': sub_cus.total_amount,
                                                                        'invoice_id': invoice[0].id,
                                                                        'invoice_amount': 0.0,
                                                                        'sale_id': order.id,
                                                                        })

                    else:

                        partner = self.partner_id
                        if not order:
                            order = self.env['sale.order'].sudo().create({
                                # 'partner_id': self.partner_id.id,
                                'partner_id': partner.id,
                                'partner_invoice_id': partner.id,
                                'partner_shipping_id': partner.id,
                                'pricelist_id': self.env.ref('product.list0').id,
                                'picking_policy': 'direct',
                                'company_id': line.sudo().company_ids.id,
                                'order_id': self.id,
                                'warehouse_id': line.sudo().warehouse.id,
                                # 'warehouse_id': 1,
                            })
                        su_taxes = self.env['account.tax']
                        for each_tax in line.tax_ids:
                            su_taxes += self.env['account.tax'].search(
                                [('name', '=', order.name), ('type_tax_use', '=', 'sale'),
                                 ('company_id', '=', order.company_id.id)])

                        sale_line = self.env['sale.order.line'].create({'name': line.product_id.name,
                                                                        'product_id': line.product_id.id,
                                                                        'product_uom_qty': line.product_uom_qty / 2,
                                                                        # 'product_uom_qty': qty,
                                                                        # 'basic_price': sub_cus.basic_value,
                                                                        'product_uom': line.product_uom.id,
                                                                        # 'price_uint': line.price_total,
                                                                        'price_unit': line.price_unit,
                                                                        # 'tax_id': [(6, 0, line.tax_ids.ids)],
                                                                        'tax_id': [(6, 0, su_taxes.ids)],
                                                                        'customer_lead': line.product_id.sale_delay,
                                                                        'taluk':line.taluks.id or line.dippo_id.taluks.id,
                                                                        'order_id': order.id})
                        # sale_line.price_unit = line.price_total / 2
                        # sale_line.price_unit = sub_cus.amount
                        order.sudo().action_confirm()
                        # for pickings in order.picking_ids:
                        #     pickings.action_assign()
                        #     pickings.button_validate()
                        order.ref = order.name[-4:]
                        if self.sale_date:
                            order.confirmation_date = self.sale_date
                        # order.create_invoices()
                        # invoice = order.sudo().action_invoice_create()
                        invoice = order.sudo()._create_invoices()
                        # inb = self.env['account.move'].browse(invoice[0])
                        inb = invoice
                        inb.account_id = self.env['account.account'].search(
                            [('name', '=', 'Debtors'), ('company_id', '=', inb.company_id.id)])
                        # inb.write({'tax_id': [(6, 0, line.tax_ids.ids)]})
                        acc_taxes = self.env['account.tax']
                        for each_tax in line.tax_ids:
                            acc_taxes += self.env['account.tax'].search(
                                [('name', '=', each_tax.name), ('type_tax_use', '=', 'sale'),
                                 ('company_id', '=', inb.company_id.id)])

                        # inb.write({'tax_id': [(6, 0, line.tax_ids.ids)]})
                        # inb.write({'tax_id': [(6, 0, acc_taxes.ids)]})
                        # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name', '=', 'Rounding 0.05')])
                        inb.write({'estimate_id': self.id})
                        inb.write({'est_line_id':line.id})
                        inb.write({'branch_id': line.branch_id.id})
                        inb.remarks = self.remarks
                        inb.b2b_company_name = self.partner_id.b2b_company_name
                        inb.site = self.partner_id.site
                        inb.complete_address = sub_cus.complete_address
                        for pickings in order.picking_ids:
                            if pickings.company_id == inb.company_id:
                                # inb.picking_id = pickings
                                pickings.inv_id =inb

                        # inb.action_invoice_open()
                        for v_line in inb.invoice_line_ids:
                            if v_line.product_id == line.product_id:
                                v_line.hsn_code = v_line.product_id.l10n_in_hsn_code
                                v_line.including_price = sub_cus.amount
                                inb.vehicle = line.vahicle_char.vehi_reg
                                v_line.taluk = line.taluks.id or line.dippo_id.taluks.id
                        # if inb.amount_total > round(inb.amount_total):
                        #    # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name', '=', 'Rounding 0.05')])
                        #    # # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name', '=', 'Rounding 0.05')])
                        #    # # inb._onchange_cash_rounding()
                        #    # rounding_amount = inb.cash_rounding_id.compute_difference(inb.currency_id,
                        #    #                                                           inb.amount_total)
                        #    profit_acc_name = self.env['account.account'].sudo().search(
                        #        [('company_id','=',inb.company_id.id),('name', '=', self.env['account.cash.rounding'].search(
                        #            [('name', '=', 'Rounding 0.05')]).profit_account_id.name)])
                        #    round_acc = self.env['account.account'].search(
                        #        [('name', '=', profit_acc_name.name),
                        #         ('company_id', '=', inb.company_id.id)])
                        #
                        #    rounding_line = self.env['account.move.line'].sudo().create({
                        #        'name': 'Rounding 0.05',
                        #        'move_id': inb.id,
                        #        'account_id': round_acc.id,
                        #        # 'loss_account_id': self.env['account.cash.rounding'].search(
                        #        #     [('name', '=', 'Rounding 0.05')]).loss_account_id.id,
                        #        'price_unit': -(inb.amount_total - round(inb.amount_total)),
                        #        'quantity': 1,
                        #        'is_rounding_line': True,
                        #        'sequence': 9999  # always last line
                        #    })

                           # To be able to call this onchange manually from the tests,
                           # ensure the inverse field is updated on account.move.
                           # inb.invoice_line_ids += rounding_line
                        # else:
                        #     if inb.amount_total < round(inb.amount_total):
                        #        # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name', '=', 'Rounding 0.05')])
                        #        # # inb.cash_rounding_id = self.env['account.cash.rounding'].search([('name', '=', 'Rounding 0.05')])
                        #        # # inb._onchange_cash_rounding()
                        #        # rounding_amount = inb.cash_rounding_id.compute_difference(inb.currency_id,
                        #        #                                                           inb.amount_total)
                        #
                        #        profit_acc_name = self.env['account.account'].sudo().search(
                        #            [('company_id','=',inb.company_id.id),('name', '=', self.env['account.cash.rounding'].search(
                        #                [('name', '=', 'Rounding 0.05')]).profit_account_id.name)])
                        #        round_acc = self.env['account.account'].search([('name','=',profit_acc_name.name),('company_id','=',inb.company_id.id)])
                        #
                        #
                        #        rounding_line = self.env['account.move.line'].sudo().create({
                        #            'name': 'Rounding 0.05 Up',
                        #            'move_id': inb.id,
                        #            # 'account_id': self.env['account.cash.rounding'].search(
                        #            #     [('name', '=', 'Rounding up 0.05')]).account_id.id,
                        #            'account_id':round_acc.id,
                        #            # 'loss_account_id':self.env['account.account'].search(
                        #            #     [('name', '=', 'Rounding up 0.05')]).loss_account_id.id,
                        #            'price_unit': round(inb.amount_total)-inb.amount_total,
                        #            'quantity': 1,
                        #            'is_rounding_line': True,
                        #            'sequence': 9999  # always last line
                        #        })

                               # To be able to call this onchange manually from the tests,
                               # ensure the inverse field is updated on account.move.
                               # inb.invoice_line_ids += rounding_line

                        if self.sale_date:
                            inb.invoice_date = self.sale_date
                        if order.ref:
                            inb.ref= order.ref

                        # inb.action_invoice_open()
                        inb.sudo().action_post()
                        # lines = (0, 0, {'name': line.product_id.name,
                        #                 'product_id': line.product_id.id,
                        #                 'product_uom_qty': line.price_total/2,
                        #                 'product_uom': line.product_uom.id,
                        #                 'customer_lead': line.product_id.sale_delay})
                        # list.append(lines)
                        # if self.payment_type == 'credit':
                        #     partner = self.env['res.partner'].search([('name','=','credit customer')])
                        # else:
                        # partner = self.env['res.partner'].search([('name','=','cash customer')])
                        # remaing_qty = round(line.product_uom_qty-qty)
                        # order_1 = self.env['sale.order'].create({
                        #     'partner_id': partner.id,
                        #     'partner_invoice_id': partner.id,
                        #     'partner_shipping_id': partner.id,
                        #     'pricelist_id': self.env.ref('product.list0').id,
                        #     'picking_policy': 'direct',
                        #     'company_id': line.company_ids.id,
                        #     'order_id': self.id,
                        #     'warehouse_id': line.warehouse.id,
                        #     'ship_to':self.ship_to,
                        # })
                        # sale_lines = self.env['sale.order.line'].create({'name': line.product_id.name,
                        #                 'product_id': line.product_id.id,
                        #                 # 'product_uom_qty': line.product_uom_qty/2,
                        #                 'product_uom_qty': remaing_qty,
                        #                 'product_uom': line.product_uom.id,
                        #                  # 'price_uint': line.price_total / 2,
                        #                  'price_uint': line.price_unit,
                        #                 'customer_lead': line.product_id.sale_delay,
                        #                                     'order_id':order_1.id})
                        # # sale_lines.price_unit = line.price_total / 2
                        # sale_lines.price_unit = line.price_unit
                        # order_1.action_confirm()
                        self.env['estimate.balance'].create({'estimate': self.id,
                                                             'estimate_line': line.id,
                                                             'product_id': line.product_id.id,
                                                             'quantity': line.product_uom_qty,
                                                             'partner_id': self.partner_id.id,
                                                             'date': datetime.today().date(),
                                                             'balance': line.price_unit - line.inv_price
                                                             })

                        est = self.env['estimate.analysis'].create({'estimate': self.id,
                                                                    'estimate_line': line.id,
                                                                    'company_id': line.company_ids.id,
                                                                    'product_id': line.product_id.id,
                                                                    'quantity': line.product_uom_qty,
                                                                    'partner_id': self.partner_id.id,
                                                                    # 'sub_partner_id': partner.id,
                                                                    'date': datetime.today().date(),
                                                                    'b_to_b': partner.b_to_b,
                                                                    'amount': line.price_total,
                                                                    'invoice_amount': 0.0,
                                                                    'invoice_id': invoice[0].id,
                                                                    'sale_id': order.id,
                                                                    # 'estimate_amount': line.price_total,
                                                                    })

                    if est:
                        est = self.env['estimate.analysis'].create({'estimate': self.id,
                                                                    'estimate_line': line.id,
                                                                    'company_id': line.company_ids.id,
                                                                    'product_id': line.product_id.id,
                                                                    'quantity': line.product_uom_qty,
                                                                    'partner_id': self.partner_id.id,
                                                                    'date': datetime.today().date(),
                                                                    'b_to_b': self.partner_id.b_to_b,
                                                                    'amount': 0.0,
                                                                    'estimate_amount': line.price_total,
                                                                    'invoice_amount': 0.0,
                                                                    'invoice_id': invoice[0].id,
                                                                    'sale_id': order.id,
                                                                    })
                # else:
                #     self.create_subcompany_so(line)

            for line in self.estimate_ids:
                old_record = self.env['budget.report'].search(
                    [('product_id', '=', line.product_id.id), ('date', '=', datetime.today().date())])
                # if not old_record:
                #     self.env['budget.report'].create({
                #         'date': datetime.today().date(),
                #         'product_id': line.product_id.id,
                #         'product_so_qty': line.product_uom_qty,
                #         'avg_sold_price': line.price_total / line.product_uom_qty,
                #         'price_so_subtotal': line.price_total,
                #     })
                # else:

                if old_record:
                    old_set_price = old_record.filtered(lambda a: a.set_selling_price > 0)
                    if old_set_price:
                        old_record = old_set_price[0]
                        if old_record[0].set_selling_price > line.price_unit:
                            if self.owner_status != 'approve':
                                raise ValidationError(_(
                                    "Today Selling price is %s/- but your selling with the price of  %s/-.\n Please take permission from Owner") % (
                                                          old_record.set_selling_price, line.price_unit))

                    old_record[0].product_so_qty += line.product_uom_qty
                    old_record[0].price_so_subtotal += line.price_total
                    old_record[0].avg_sold_price = old_record[0].price_so_subtotal / old_record[0].product_so_qty
                # return super(SaleEstimate, self).action_approve()

            # if expense:
            #     product = self.env['product.product'].search([('name', '=', 'Expense')])
            #     hr = self.env['hr.expense'].create({
            #         'product_id': product.id,
            #         'quantity': 1,
            #         'unit_amount': expense,
            #         'name': 'Vahicle Expenses',
            #         'estimate_ref': self.name,
            #     })
            # if inb:
               # acc = inb.invoice_line_ids.account_id
               # debit = sum(acc.mapped('debit'))
               # credit = sum(acc.mapped('credit'))
               # open_bal = debit-credit
               # exp = sum(self.estimate_ids.mapped('exp_inv_price'))
               # sale = sum(self.estimate_ids.mapped('price_total'))
               # # sale = sum(self.estimate_ids.mapped('sub_customers').mapped('total_amount'))
               # self.env['balance.analysis'].create({'account_id':inb.invoice_line_ids.account_id.id,
               #                                      'date':date.today(),
               #                                      'opening_balance':open_bal,
               #                                      'sale_amount':sale,
               #                                      'expense_amount':exp,
               #                                      # 'purchase_amount':
               #                                      'current_bal':open_bal+sale-exp,
               #
               #                                      })

            # self.write({'status': 'done'})
            self.total_done = sum(self.estimate_ids.mapped('done_qty'))
            self.balance_qty = sum(self.estimate_ids.mapped('bal_qty'))
            if self.total_done == sum(self.estimate_ids.mapped('product_uom_qty')):
                self.write({'status': 'done'})
            bal_list = []
            if self.balance_qty:
                est_back_id = self.env['sale.estimate'].create({
                    'partner_id': self.partner_id.id,
                    'ship_to': self.ship_to,
                    'backorder_id': self.id,
                })


                for line in self.estimate_ids:
                    self.env['sale.estimate.lines'].create({'product_id': line.product_id.id,
                            'estimate_line_id': line.id,
                            'product_uom': line.product_id.uom_id.id,
                            'product_uom_qty':line.bal_qty,
                            'price_unit':line.price_unit,
                            'company_ids':[(6, 0, line.company_ids.ids)],
                            'warehouse':[(6, 0, line.warehouse.ids)],
                            'estimate_id':est_back_id.id,
                    })
            self.write({'status': 'done'})
        # if self.backorder_id:
        #     print('jknklmlm')

        self.action_partner_ledger()
        self.action_partner_ledgers()
        # self.action_product_profit()

        rent_lines_list = []

        j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
        if self.direct_sale == True:
            entry = self.env['data.entry'].create(
                {'user_id': self.user_id.id, 'partner_id': self.partner_id.id, 'payment_method_id': j.id})
            for exp in self.estimate_ids:
                journal = self.env['account.journal'].search(
                    [('name', '=', 'Cash'), ('company_id', '=', self.company_id.id)])

                line = (0, 0, {
                    'partner_id': self.partner_id.id,
                    'date': self.c_date,
                    'journal_id': journal.id,
                    'invoice_id': self.total_invoice.id,
                    'estimate_id': self.id,
                    'vehicle_id': exp.vahicle.id,
                    'balance_amount': sum(self.mapped('estimate_ids').mapped('price_total')),
                })
                rent_lines_list.append(line)
            entry.partner_invoices = rent_lines_list
        self.create_purchase_remainder()
        if self.sale_orders:
            self.picking_ids = self.sale_orders.mapped('picking_ids').filtered(
                lambda a: a.company_id != self.company_id)
