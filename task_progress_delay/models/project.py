# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime, date
from datetime import time
from odoo.tools.translate import _
from odoo.exceptions import Warning
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta


class Project(models.Model):
    _inherit = "project.project"

    prefix_code = fields.Char(string='Prefix Code', required=True)
    category = fields.Selection(
        [('employee', 'Employee'), ('clients', 'Clients'), ('admin', 'Admin'), ('employees', 'Employees'), ],
        string='Category')
    sla_in_hours = fields.Float(string='SLA(in hours)')
    turnaround_time_days = fields.Float(string='TurnAround Time(in days)')
    turnaround_time_hours = fields.Float(string='TurnAround Time(in hours)', compute='_get_turnaround_hours')
    product_id = fields.Many2one('product.template', string="Workflow Product")
    product_id_govt_fee = fields.Many2one('product.template', string="Product for Government Fee")

    def _get_turnaround_hours(self):
        self.turnaround_time_hours = 0
        company_id = self.env.company.id
        resource = self.env['resource.calendar'].search(
            [('company_id', '=', company_id), ('company_calendar', '=', True)])
        for project in self:
            # for i in resource:
            if resource:
                project.turnaround_time_hours = project.turnaround_time_days * resource.hours_per_day


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    stage_name = fields.Many2one('project.task.type', string="Stage Name", domain="[('project_ids', '=', project_id)]")
    cost_stage = fields.Float(string='Tasc Fee')
    check_entered = fields.Boolean(string='Check')
    gov_fee = fields.Float(string='Government Fee')
    turn_time = fields.Float(related='stage_name.lead_time', string='Turnaround Time')
    time_hours = fields.Float(string='Turnaround Time', compute='calculate_task_progress_yes')
    task_allocation = fields.Float(string='Turnaround Time', compute='calculate_task_progress_yes')
    delay_color = fields.Char(string='Delay Color', compute='calculate_delay_task_report')

    def calculate_delay_task_report(self):
        self.delay_color = 0
        for rec in self:
            resource = self.env['resource.calendar'].search(
                [('company_id', '=', self.company_id.id), ('company_calendar', '=', True)])
            if resource:
                time_hours = rec.turn_time * resource.hours_per_day
                if rec.unit_amount > time_hours:
                    rec.delay_color = 'True'
        return True

    @api.depends('stage_id')
    def calculate_progress(self):
        self.task_progress = 0
        for self in self:
            for rec in self.timesheet_ids:
                if rec.stage_name.lead_time != 0:
                    company_id = self.env.company.id
                    resource = self.env['resource.calendar'].search(
                        [('company_id', '=', company_id), ('company_calendar', '=', True)])
                    if resource:
                        time_hours = rec.unit_amount / resource.hours_per_day
                        # print('rec.time_hours',time_hours)
                        rec.time_hours = rec.time_hours / rec.stage_name.lead_time
                        rec.task_allocation = rec.stage_name.allocation * rec.time_hours
        return True

    def calculate_task_progress_yes(self):
        self.time_hours = 0
        self.task_allocation = 0
        for rec in self:
            if rec.stage_name.lead_time != 0:
                company_id = self.env.company.id
                resource = self.env['resource.calendar'].search(
                    [('company_id', '=', company_id), ('company_calendar', '=', True)])
                if resource:
                    time_hours = rec.unit_amount / resource.hours_per_day
                    # print('rec.time_hours',time_hours)
                    rec.time_hours = time_hours / rec.stage_name.lead_time
                    rec.task_allocation = rec.stage_name.allocation * rec.time_hours
        return True


# stage_name = fields.Many2one(string="Stage Name", related='task_id.stage_id.name',readonly=True)
# task_name = fields.Many2one('project.task.type')


class projectTaskType(models.Model):
    _inherit = 'project.task.type'

    lead_time = fields.Float('Turnaround Time')
    allocation = fields.Float('Allocation in project')
    product_id = fields.Many2one('product.template', string="Workflow Product",
                                 domain=[('categ_id.name', '=', 'Workflow')])


class ProjectTask(models.Model):
    _inherit = 'project.task'

    task_code = fields.Char(string="Task Number")
    task_stage = fields.Char(string="Stage Name", related='stage_id.name')
    type = fields.Selection(
        [('monthlyretainer', 'Monthly Retainer'), ('payasyougo', 'Pay as you go'), ('hybrid', 'Hybrid'), ],
        string='Type', related='partner_id.customer_def_type')
    task_progress = fields.Float(string="Task Progress",compute='calculate_progress', store=True)
    progress_histogry_ids = fields.One2many('task.progress.history', 'task_id')
    prefix_code = fields.Char(string='Prefix Code')
    planned_hours = fields.Float(related='project_id.turnaround_time_days',
                                 help='Time planned to achieve this task (including its sub-tasks).', readonly="0",
                                 tracking=True)
    planned_days_project = fields.Float(related='project_id.turnaround_time_days', string='Turnaround Time (in Days)')
    delay_notify = fields.Char(string='Delay Color', compute='calculate_time_delay')
    stage_delay = fields.Char(string='Delay in stage', compute='calculate_stage_delay')
    total_cost = fields.Float(string="Total Cost", default=0.0, compute='calculate_task_cost')
    total_task_cost = fields.Float(string="Total Tasc Fee", default=0.0, compute='calculate_task_cost')
    total_govt_fee = fields.Float(string="Total Government Fee", default=0.0, compute='calculate_task_cost')
    # date_deadline = fields.Datetime(string="Date Deadline", compute='get_date_deadline')
    planned_date_begin = fields.Datetime("Start date")
    planned_date_end = fields.Datetime("End date", store=True)
    stage_lead_time = fields.Float(related='stage_id.lead_time', string='Stage Turnaround Time')
    check_closing_stage = fields.Boolean('Check Closing Stage', default=False, compute='compute_closing_stage')

    # @api.onchange('planned_date_end')
    # def _change_deadline(self):
    # 	for i in self:
    # 		i.date_deadline = i.planned_date_end

    def compute_closing_stage(self):
        for rec in self:
            if rec.stage_id:
                rec.check_closing_stage = rec.stage_id.is_closed

    def action_create_invoice(self):
        cost_stage_fee = []
        govt_stage_fee = []
        for fee in self.timesheet_ids:
            cost_stage_fee.append(fee.cost_stage)
            govt_stage_fee.append(fee.gov_fee)
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.project_id.product_id.id,
                'quantity': 1,
                'price_unit': sum(cost_stage_fee),
            }), (0, 0, {
                'name': '',
                'product_id': self.project_id.product_id_govt_fee.id,
                'quantity': 1,
                'price_unit': sum(govt_stage_fee)
            })]
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Invoice',
            'res_model': 'account.move',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain': [('id', '=', invoice.id)],
            'res_id': invoice.id,
            'target': 'current',
        }

    def open_task_report(self):
        timesheet = self.env['account.analytic.line'].search([])
        domains = []
        for rec in timesheet:
            if rec.task_id.delay_notify == self.delay_notify:
                domains.append(rec.id)
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.analytic.line',
                    'target': 'current',
                    'view_id': self.env.ref('hr_timesheet.hr_timesheet_line_tree').id,
                    'view_mode': 'tree',
                    'context': {'group_by': 'task_id'},
                    'domain': [('task_id', '=', self.id)],
                    'res_id': rec.id,
                }

    @api.onchange('planned_date_begin')
    @api.depends('planned_date_begin')
    def get_date_deadline(self):
        # self.date_deadline = False
        self.planned_date_end = False
        for self in self:
            if self.planned_date_begin != False or self.planned_date_end != False:
                # datetime_str = '09/19/18 13:55:26'
                string_start = str(self.planned_date_begin)
                datetime_object = datetime.strptime(string_start, '%Y-%m-%d %H:%M:%S')
                date_deadline = timedelta(days=int(self.planned_days_project))
                date_deadline_final = datetime_object + date_deadline
                if date_deadline_final.isoweekday() == 5:
                    self.date_deadline = date_deadline_final + timedelta(days=2)
                    self.planned_date_end = date_deadline_final + timedelta(days=2)
                elif date_deadline_final.isoweekday() == 6:
                    self.date_deadline = date_deadline_final + timedelta(days=1)
                    self.planned_date_end = date_deadline_final + timedelta(days=1)
                else:
                    self.date_deadline = date_deadline_final
                    self.planned_date_end = date_deadline_final

    #  aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',self.stage_id.id)
    # if j.stage_name.name != self.task_stage:
    # 	raise Warning(_('"Please Fill the Stage Name"'))
    # 	# if not j.cost_stage:
    # 	# 	raise Warning(_('"Please Fill the Cost"'))

    def calculate_task_cost(self):
        self.total_task_cost = 0
        self.total_govt_fee = 0
        self.total_cost = 0
        for rec in self:
            tasks = self.env['account.analytic.line'].search([('task_id', '=', rec.id)])
            if tasks:
                for task in tasks:
                    rec.total_task_cost += task.cost_stage
                    rec.total_govt_fee += task.gov_fee
                    rec.total_cost = rec.total_task_cost + rec.total_govt_fee

    # @api.onchange('effective_hours')
    def calculate_time_delay(self):
        self.delay_notify = 0
        for rec in self:
            resource = self.env['resource.calendar'].search(
                [('company_id', '=', self.company_id.id), ('company_calendar', '=', True)])
            if resource:
                time_hours = rec.planned_hours * resource.hours_per_day
                if rec.effective_hours > time_hours:
                    rec.delay_notify = 'True'
        return True

    def calculate_stage_delay(self):
        self.stage_delay = 0
        for rec in self:
            resource = self.env['resource.calendar'].search(
                [('company_id', '=', self.company_id.id), ('company_calendar', '=', True)])
            if resource:
                time_hours = rec.stage_lead_time * resource.hours_per_day
                if rec.effective_hours > time_hours:
                    rec.stage_delay = 'True'
        return True

    @api.model
    def create(self, vals):
        # assigning the sequence for the record
        # if vals.get('code', _('New')) == _('New'):
        res = super(ProjectTask, self).create(vals)
        for j in self.timesheet_ids:
            if not j.cost_stage or j.unit_amount:
                # raise Warning(_('"Please Fill the Cost and Duration"'))
                print('removeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeed as its not working')

        project = self.env['project.project'].search([('name', '=', res.project_id.name)])
        if project:
            res.write({'prefix_code': project.prefix_code,
                       })
            vals['task_code'] = self.env['ir.sequence'].next_by_code('project.task')
            seq = vals['task_code'].replace('TASK', res.prefix_code)
            res.write({
                'task_code': seq,
            })
        return res

    #
    # @api.depends('stage_id')
    # def calculate_progress(self):
    #     self.task_progress = 0
    #     for rec in self:
    #         if rec.stage_id and rec.stage_id.sequence == 0:
    #             print('whyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy',rec.stage_id)
    #             rec.task_progress = 0.0
    #         else:
    #             stages = self.env['project.task.type'].search([])
    #             prev_stages = []
    #             for stage in stages:
    #                 if rec.project_id in stage.project_ids and stage.sequence < rec.stage_id.sequence:
    #                     prev_stages.append(stage)
    #             for prev_stage in prev_stages:
    #                 prev_alloc =d
    #                 rec.task_progress = rec.task_progress + prev_stage.allocation
    #     return True
    
    def calculate_progress(self):
        taskk_time = []
        duration = []
        timesheet_id = []
        sstages_id = []
        check_timsesheet_id = []

        for selfs in self:
            for rec in self.timesheet_ids:
                if rec.unit_amount > 0:
                    timesheet_id.append(self.stage_id.id)
                    duration.append(rec.unit_amount)
                    check_timsesheet_id.append(rec.stage_name.id)
            for rec in selfs.timesheet_ids:
                stage_ids = self.env['project.task.type'].search([('id', 'in', check_timsesheet_id)])
                for ss in stage_ids:
                for stage_id in stage_ids:
                    if rec.stage_name.name == self.task_stage:
                        total = sum(duration)
                        if stage_id:
                            if stage_id.lead_time:
                                company_id = self.env.company.id
                                resource = self.env['resource.calendar'].search(
                                    [('company_id', '=', company_id), ('company_calendar', '=', True)])
                                if resource:
                                    total_lead = stage_id.lead_time * resource.hours_per_day
                                    if total <= total_lead:
                                        task_progresses = total / total_lead
                                        task_progress = (task_progresses * stage_id.allocation)
                                    else:
                                        task_progress = stage_id.allocation
                                    taskk_time.append(task_progress)
                                    sstages_id.append(stage_id.name)

        for selfs in self:
            selfs.task_progress = sum(taskk_time)
        return True

#     @api.onchange('stage_id')
#     @api.depends('stage_id','task_stage','project_id')
#     def calculate_progress(self):
#         # self.task_progress = 0
#         total = 0
#         duration = []
#         timesheet_id = []
#         for self in self:
#             total_duration = 0
#             for rec in self.timesheet_ids:
#                 print('kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk', self.stage_id.id)
#                 print('kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk', self.task_stage)
#                 print('rec.stage_name.name', rec.stage_name.name)
#                 print('kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk', self.task_progress)
#                 timesheet_id.append(rec.stage_name.id)
#                 print('timesheeeeeeeeeeeeeeeeeeeetlissssssssssst',timesheet_id)
#                 stage_id = self.env['project.task.type'].search([('name', '=', self.task_stage),
#                                                                  ('project_ids', '=', self.project_id.name)])
#                 if rec.stage_name.name == self.task_stage:
#                     print('rec.check_entered',rec.check_entered)
#                     if rec.check_entered != True:
#                         print('reccccccccccccccccccccccccccccccccccc', rec.unit_amount)
#                         # total_duration += rec.unit_amount
#                         duration.append(rec.unit_amount)
#                         print('duraaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', duration)
#                         total = sum(duration)
#                         print('ttttttttttttttttttttttttttttttttttttttttttttttt', total)
#                         if stage_id:
#                             print('stageleadtimeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', stage_id.lead_time)
#                             if stage_id.lead_time != 0:
#                                 company_id = self.env.company.id
#                                 resource = self.env['resource.calendar'].search(
#                                     [('company_id', '=', company_id), ('company_calendar', '=', True)])
#                                 if resource:
#                                     total_lead = stage_id.lead_time * resource.hours_per_day
#                                     print('totalleaddddddddddddddddddddddddddddddd', total_lead)
#                                     if total >= total_lead:
#                                         self.task_progress += stage_id.allocation
#                                         rec.check_entered = True
#                                     else:
#                                         task_progress = total / total_lead
#                                         self.task_progress += task_progress * stage_id.allocation
#                                         rec.check_entered = True
#                                         print('elssssssssssssssssssssssssssssse', self.task_progress)
#         # return True
#         for self in self:
#             total_duration = 0
#             for rec in self.timesheet_ids:
#                 print('kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk', self.task_stage)
#                 stage_id = self.env['project.task.type'].search(
#                     [('name', '=', self.task_stage), ('project_ids', '=', self.project_id.name)])
#                 if rec.stage_name.name == self.task_stage:
#                     print('reccccccccccccccccccccccccccccccccccc', rec.unit_amount)
#                     # total_duration += rec.unit_amount
#                     duration.append(rec.unit_amount)
#                     print('duraaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', duration)
#                     total = sum(duration)
#                     print('ttttttttttttttttttttttttttttttttttttttttttttttt', total)
#                     if stage_id:
#                         print('stageleadtimeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', stage_id.lead_time)
#                         if stage_id.lead_time != 0:
#                             company_id = self.env.company.id
#                             resource = self.env['resource.calendar'].search(
#                                 [('company_id', '=', company_id), ('company_calendar', '=', True)])
#                             if resource:
#                                 total_lead = stage_id.lead_time * resource.hours_per_day
#                                 print('totalleaddddddddddddddddddddddddddddddd', total_lead)
#                                 if total >= total_lead:
#                                     self.task_progress = stage_id.allocation
#                                 else:
#                                     task_progress = total / total_lead
#                                     self.task_progress = task_progress * stage_id.allocation
#                                     print('elssssssssssssssssssssssssssssse', self.task_progress)
#                 # else:
#                 #     Progress = (Sum(Duration in Days stage) / Turnaroundtimestage)*allocation % age
#         return True

    def write(self, vals):
        if vals.get('stage_id', False):
            total_time = 0
            if len(self.timesheet_ids) == 0:
                raise Warning(_('"Please Fill the task cost or Government fee"'))
            stage_ids = []
            for stage_id in self.timesheet_ids:
                stage_ids.append(stage_id.stage_name.id)
            for j in self.timesheet_ids:
                stage_ids.append(j.stage_name.id)
                if self.stage_id.id not in stage_ids:
                    raise Warning(_('Please ensure that you have entered all relevant costs before moving to the next activity/step'))
                if j.cost_stage + j.gov_fee == 0:
                    raise Warning(_('Please ensure that you have entered all relevant costs before moving to the next activity/step'))
                if self.stage_id.name == j.stage_name.name:
                    total_time += j.unit_amount
                history_vals = {
                    'stage_from_id': self.stage_id.id,
                    'stage_to_id': vals['stage_id'],
                    'task_id': self.id,
                    'date': fields.Date.today(),
                    'time_taken': total_time,
                }
                vals['progress_histogry_ids'] = [(0, 0, history_vals)]
        return super(ProjectTask, self).write(vals)

    # def write(self, vals):
    #     if vals.get('stage_id', False):
    #         total_time = 0
    #         for j in self.timesheet_ids:
    #             if not j.cost_stage:
    #                 raise Warning(_('"Please Fill the Cost"'))
    #             if self.stage_id.name == j.stage_name.name:
    #                 total_time += j.unit_amount
    #             history_vals = {
    #                 'stage_from_id': self.stage_id.id,
    #                 'stage_to_id': vals['stage_id'],
    #                 'task_id': self.id,
    #                 'date': fields.Date.today(),
    #                 'time_taken': total_time,
    #             }
    #             vals['progress_histogry_ids'] = [(0, 0, history_vals)]
    #     return super(ProjectTask, self).write(vals)


class taskProgressHistory(models.Model):
    _name = 'task.progress.history'
    _description = 'Task Progress History'

    task_id = fields.Many2one('project.task')
    stage_from_id = fields.Many2one('project.task.type', string='From Stage')
    stage_to_id = fields.Many2one('project.task.type', string='To Stage')
    date = fields.Date('Date Completed')
    delay = fields.Integer(string='Delay', compute='calculate_time_delay')
    time_taken = fields.Float(string='Time Elapsed')
    delay_color = fields.Char(string='Delay Color', compute='calculate_time_taken')

    def calculate_time_delay(self):
        self.delay = 0
        for rec in self:
            rec.delay = rec.stage_from_id.lead_time - rec.time_taken
        return True

    def calculate_time_taken(self):
        self.delay_color = 0
        for rec in self:
            if rec.delay < 0:
                rec.delay_color = 'True'
        return True


class Worked_schedule(models.Model):
    _inherit = "resource.calendar"

    company_calendar = fields.Boolean(string='Company Calendar')
