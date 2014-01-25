import json
#from collections import Mapping

from django.shortcuts import render_to_response
from django.views.generic import View  #, TemplateView
from django.template.response import TemplateResponse
from django.template.loader import get_template
from django.http import Http404

from pug.nlp import parse
#from pug.nlp.util import normalize_scientific_notation
#from pug.nlp.character_subset import digits
from pug.nlp import util
from pug.nlp import db
#count_in_category, count_in_date, sum_in_date, lagged_in_date, align_time_series, listify, datetime_in_milliseconds, best_scale_factor, round_to_sigfigs


def home(request, graph_uri=None):
    """home page"""
    graph_uri = graph_uri or r'Origin,3,1_I,2,2_10~Origin_II,2~I_III~I_IV~II_IV~IV_V~V_I~VI_V,.5,3~VII,.2,4_V'
    data = {
        'graph_uri': graph_uri,
        }
    return render_to_response('miner/home.html', data)


def url_graph(request, chart_type='lineWithFocusChart', values_list=('modified'), filter_dict={'title__startswith': 'E'}, model='WikiItem'):
    """
    Send data in the context variable "data" for a pie chart (x, y) and a line chart.
    """

    graph_uri = r'Origin,3,1_I,2,2_10~Origin_II,2~I_III~I_IV~II_IV~IV_V~V_I~VI_V,.5,3~VII,.2,4_V'
    data = {
        'graph_uri': graph_uri,
    }
    return render_to_response('miner/chart.html', data)


def connections(request, edges):
    """
    Plot a force-directed graph based on the edges provided
    """
    edge_list, node_list = parse.graph_definition(edges)
    data = {'nodes': json.dumps(node_list), 'edges': json.dumps(edge_list)}
    return render_to_response('miner/connections.html', data)

def stats(request, date_offset=0, fields=None, title_prefix=None, model='WikiItem'):
    """
    In addition to chart data in data['chart'], send statistics data to view in data['stats']
    """
    data = {}

    modified_chart_data = data['chart']['chartdata']
    if 'y2' in data['chart']['chartdata']:
        matrix = db.Columns([modified_chart_data['y1'], modified_chart_data['y2']], ddof=0, tall=True)
    else:
        fields = ['date/time'] + fields
        matrix = db.Columns([modified_chart_data['x'], modified_chart_data['y']], ddof=0, tall=True)
    if fields and len(fields) > 1:
        fields = fields[:2]
    else:
        fields = [
            data['chart']['chartdata'].get('name1') or 'time',
            data['chart']['chartdata'].get('name2') or data['chart']['chartdata'].get('name') or 'value',
            ]
    fields = util.pluralize_field_names(fields)
    data.update({
        'stats': {
            'fields': fields,
            'heading': 'Statistics',
            'cov': zip(fields, matrix.cov()),
            'R': zip(fields, matrix.rho),
            },
        })
    data['chart']['chartdata'] = modified_chart_data
    data['chart']['chart_title'] = 'Time Series'
    return render_to_response('miner/stats.html', data)


class StaticView(View):
    def get(self, request, *args, **kwargs):
        template_name = ''
        try:
            template_name += 'miner/staticview/' + kwargs.get('page', '') + '.html'
            get_template(template_name) 
        except:
            raise Http404()
        return TemplateResponse(request, template_name)

# # def parse_node_name(name, use_defaults=False):
# #     """
# #     >>> sorted(parse_node_name('Origin,2.7, 3 ')[1].items())
# #     [('charge', 2.7), ('group', 3), ('name', 'Origin')]
# #     >>> parse_node_name('Origin,2.7, 3 ')[0]
# #     'Origin'
# #     """
# #     # if the name is not a string, but a dict defining a node, then just set the defaults and return it
# #     if isinstance(name, Mapping):
# #         ans = dict(name)
# #         for j, field in enumerate(parse_node_name.schema):
# #             if field['key'] not in ans:
# #                 ans[field['key']] = field['default']
# #         return ans
# #     seq = listify(name, delim=',')
# #     ans = {}
# #     for j, field in enumerate(parse_node_name.schema):
# #         if 'default' in field:
# #             try:
# #                 ans[field['key']] = field['type'](seq[j])
# #             except:
# #                 if use_defaults:
# #                     ans[field['key']] = field['default']
# #         else:
# #             try:
# #                 ans[field['key']] = ans.get(field['key'], field['type'](seq[j]))
# #             except:
# #                 pass
# #     return ans
# # parse_node_name.schema = (
# #                 {'key': 'name', 'type': str},  # TODO: use the absence of a default value (rather than index > 0) to identify mandatory fields
# #                 {'key': 'charge', 'type': float, 'default': 1},
# #                 {'key': 'group', 'type': intify, 'default': 0},  # TODO: this should be a string like the names/indexes to nodes (groups are just hidden nodes)
# #               )
