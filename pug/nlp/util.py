#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''Utilities to support natural language processing:

* Vocabulary dimension reduction
* Word statistics calculation
* Add a timezone to a datetime
* Slice a django queryset
* Genereate batches from a long list or sequence
* Inverse dict/hashtable lookup
* Generate a valid python variable or class name from a string
* Generate a slidedeck-compatible markdown from an text or markdown outline or list
* Convert a sequence of sequences to a dictionary of sequences
* Pierson correlation coefficient calculation
* Parse a string into sentences or tokens
* Table (list of list) manipulation

'''

import os
import collections
from itertools import islice
import datetime
import time
import pytz
import dateutil
import types
import re
import string
import csv
import warnings
from collections import OrderedDict
from traceback import print_exc
import ascii
import decimal
import random
from decimal import Decimal
import math
import pandas as pd
from dateutil.parser import parse as parse_date

from progressbar import ProgressBar
from pytz import timezone
#import numpy as np
# import scipy as sci
from fuzzywuzzy import process as fuzzy
# import nltk
from slugify import slugify
# from sklearn.feature_extraction.text import TfidfVectorizer

import character_subset as chars
import regex_patterns as RE

import logging
logger = logging.getLogger('pug.nlp.util')


#from django.core.exceptions import ImproperlyConfigured
# try:
#     import django.db
# except ImproperlyConfigured:
#     import traceback
#     print traceback.format_exc()
#     print 'WARNING: The module named %r from file %r' % (__name__, __file__)
#     print '         can only be used within a Django project!'
#     print '         Though the module was imported, some of its functions may raise exceptions.'



ROUNDABLE_NUMERIC_TYPES = (float, long, int, decimal.Decimal, bool)
FLOATABLE_NUMERIC_TYPES = (float, long, int, decimal.Decimal, bool)
BASIC_NUMERIC_TYPES = (float, long, int) 
SCALAR_TYPES = (float, long, int, decimal.Decimal, bool, complex, basestring, str, unicode)  # datetime.datetime, datetime.date
# numpy types are derived from these so no need to include numpy.float64, numpy.int64 etc
DICTABLE_TYPES = (collections.Mapping, tuple, list)  # convertable to a dictionary (inherits collections.Mapping or is a list of key/value pairs)
VECTOR_TYPES = (list, tuple)
PUNC = unicode(string.punctuation)


def fedora_password_salt(length=8, alphabet=string.letters + string.digits + './'):
    """Generate a random salt string for use in `crypt.crypt(password, salt)`"""
    return ''.join(random.choice(alphabet) for position in range(length))


# 4 types of "histograms" and their canonical name/label
HIST_NAME = {
                'hist': 'hist', 'ff':  'hist',  'fd': 'hist', 'dff':  'hist', 'dfd': 'hist', 'gfd': 'hist', 'gff': 'hist', 'bfd': 'hist', 'bff': 'hist',
                'pmf':  'pmf',  'pdf': 'pmf',   'pd': 'pmf',
                'cmf':  'cmf',  'cdf': 'cmf',
                'cfd':  'cfd',  'cff': 'cfd',   'cdf': 'cfd',
            }
HIST_CONFIG = {
    'hist': { 
        'name': 'Histogram',  # frequency distribution, frequency function, discrete ff/fd, grouped ff/fd, binned ff/fd
        'kwargs': { 'normalize': False, 'cumulative': False, },
        'index': 0,
        'xlabel': 'Bin',
        'ylabel': 'Count',
        },
    'pmf': {
        # PMFs have discrete, exact values as bins rather than ranges (finite bin widths)
        #   but this histogram configuration doesn't distinguish between PMFs and PDFs, 
        #   since mathematically they have all the same properties. 
        #    PDFs just have a range associated with each discrete value (which should be when integrating a PDF but not when summing a PMF where the "width" is uniformly 1)
        'name': 'Probability Mass Function',   # probability density function, probability distribution [function]
        'kwargs': { 'normalize': True, 'cumulative': False, },
        'index': 1,
        'xlabel': 'Bin',
        'ylabel': 'Probability',
        },
    'cmf': {
        'name': 'Cumulative Probability',
        'kwargs': { 'normalize': True, 'cumulative': True, },
        'index': 2,
        'xlabel': 'Bin',
        'ylabel': 'Cumulative Probability',
        },
    'cfd': {
        'name': 'Cumulative Frequency Distribution',
        'kwargs': { 'normalize': False, 'cumulative': True, },
        'index': 3,
        'xlabel': 'Bin',
        'ylabel': 'Cumulative Count',
        },
    }

# MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
# MONTH_PREFIXES = [m[:3] for m in MONTHS]
# MONTH_SUFFIXES = [m[3:] for m in MONTHS]
# SUFFIX_LETTERS = ''.join(set(''.join(MONTH_SUFFIXES)))


try:
    from django.conf import settings
    DEFAULT_TZ = timezone(settings.TIME_ZONE)
except:
    DEFAULT_TZ = timezone('UTC')


def qs_to_table(qs, excluded_fields=['id']):
    rows, rowl = [], []
    qs = qs.all()
    fields = sorted(qs[0]._meta.get_all_field_names())
    for row in qs:
        for f in fields:
            if f in excluded_fields:
                continue
            rowl += [getattr(row,f)]
        rows, rowl = rows + [rowl], []
    return rows


def force_hashable(obj, recursive=True):
    """Force frozenset() command to freeze the order and contents of multables and iterables like lists, dicts, generators

    Useful for memoization and constructing dicts or hashtables where keys must be immutable.

    >>> force_hashable([1,2.,['3']])
    (1, 2.0, ('3',))    
    >>> force_hashable(i for i in range(3))
    (1, 2, 3)
    >>> from collections import Counter
    >>> force_hashable(Counter('abbccc')) ==  (('a', 1), ('c', 3), ('b', 2))
    True
    """
    try:
        hash(obj)
        return obj
    except:
        if hasattr(obj, '__iter__'):
            # looks like a Mapping if it has .get() and .items(), so should treat it like one
            if hasattr(obj, 'get') and hasattr(obj, 'items'):
                # FIXME: prevent infinite recursion:
                #        tuples don't have 'items' method so this will recurse forever if elements within new tuple aren't hashable and recurse has not been set!
                return force_hashable(tuple(obj.items()))
            if recursive:
                return tuple(force_hashable(item) for item in obj)
            return tuple(obj)
    # strings are hashable so this ends the recursion for any object without an __iter__ method (strings do not)
    return unicode(obj)


def inverted_dict(d):
    """Return a dict with swapped keys and values

    >>> inverted_dict({0: ('a', 'b'), 1: 'cd'}) == {'a': 0, 'b': 0, 'cd': 1}
    """
    return dict((force_hashable(v), k) for (k, v) in dict(d).iteritems())


def inverted_dict_of_lists(d):
    """Return a dict where the keys are all the values listed in the values of the original dict

    >>> inverted_dict_of_lists({0: ['a', 'b'], 1: 'cd'}) == {'a': 0, 'b': 0, 'cd': 1}
    True
    """
    new_dict = {}
    for (old_key, old_value_list) in dict(d).iteritems():
        for new_key in listify(old_value_list):
            new_dict[new_key] = old_key
    return new_dict


def sort_strings(strings, sort_order=None, reverse=False, case_sensitive=False, sort_order_first=True):
    """Sort a list of strings according to the provided sorted list of string prefixes

    TODO:
        - Provide an option to use `.startswith()` rather than a fixes prefix length (will be much slower)

    Arguments:
        sort_order_first (bool): Whether strings in sort_order should always preceed "unknown" strings
        sort_order (sequence of str): Desired ordering as a list of prefixes to the strings
            If sort_order strings have varying length, the max length will determine the prefix length compared
        reverse (bool): whether to reverse the sort orded. Passed through to `sorted(strings, reverse=reverse)`
        case_senstive (bool): Whether to sort in lexographic rather than alphabetic order
         and whether the prefixes  in sort_order are checked in a case-sensitive way 

    Examples:
        >>> sort_strings(['morn32', 'morning', 'unknown', 'less unknown', 'lucy', 'date', 'dow', 'doy', 'moy'], ('dat', 'dow', 'moy', 'dom', 'moy', 'mor'), reverse=True)
        ['unknown', 'morning', 'morn32', 'moy', 'lucy', 'less unkown', 'doy', 'dow', 'date']
        >>> sort_strings(['morn32', 'morning', 'unknown', 'date', 'dow', 'doy', 'moy'], ('dat', 'dow', 'moy', 'dom', 'moy', 'mor'))
        ['date', 'dow', 'doy', 'moy', 'morn32', 'morning', 'unknown']

        By default, strings whose prefixes don't exist in sort_order are interleaved into the sorted list in alphabetic order
        >>> sort_strings(['morn32', 'morning', 'unknown', 'lucy', 'less unknown', 'date', 'dow', 'doy', 'moy'], ('dat', 'dow', 'moy', 'dom', 'moy', 'mor'))
        ['date', 'dow', 'doy', 'less unknown', 'moy', 'morn32', 'morning', 'unknown']
    """
    if not case_sensitive:
        sort_order = tuple(s.lower() for s in sort_order)
        strings = tuple(s.lower() for s in strings)
    prefix_len = max(len(s) for s in sort_order)

    def compare(a, b, prefix_len=prefix_len):
        if prefix_len:
            if a[:prefix_len] in sort_order:
                if b[:prefix_len] in sort_order:
                    comparison = sort_order.index(a[:prefix_len]) - sort_order.index(b[:prefix_len])
                    comparison /= abs(comparison or 1)
                    if comparison:
                        return comparison * (-2 * reverse + 1)
                elif sort_order_first:
                    return -1
            # b may be in sort_order list, so reverse the order and find out
            elif sort_order_first:
                return - compare(b, a, prefix_len)
        return (-1 * (a < b) + 1 * (a > b)) * (-2 * reverse + 1)

    return sorted(strings, cmp=compare)


def clean_field_dict(field_dict, cleaner=unicode.strip, time_zone=None):
    r"""Normalize field values by stripping whitespace from strings, localizing datetimes to a timezone, etc

    >>> sorted(clean_field_dict({'_state': object(), 'x': 1, 'y': u"\t  Wash Me! \n" }).items())
    [('x', 1), ('y', u'Wash Me!')]
    """
    d = {}
    if time_zone is None:
        tz = DEFAULT_TZ
    for k, v in field_dict.iteritems():
        if k == '_state':
            continue
        if isinstance(v, basestring):
            d[k] = cleaner(unicode(v))
        elif isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = tz.localize(v)
        else:
            d[k] = v
    return d


# def reduce_vocab(tokens, similarity=.85, limit=20):
#     """Find spelling variations of similar words within a list of tokens to reduce token set size

#     Arguments:
#       tokens (list or set or tuple of str): token strings from which to eliminate similar spellings

#     Examples:
#       >>> reduce_vocab(('on', 'hon', 'honey', 'ones', 'one', 'two', 'three'))  # doctest: +NORMALIZE_WHITESPACE


#     """
#     tokens = set(tokens)
#     thesaurus = {}
#     while tokens:
#         tok = tokens.pop()
#         matches = fuzzy.extractBests(tok, tokens, score_cutoff=int(similarity * 100), limit=20)
#         if matches:
#             thesaurus[tok] = zip(*matches)[0]
#         else:
#             thesaurus[tok] = (tok,)
#         for syn in thesaurus[tok][1:]:
#             tokens.discard(syn)
#     return thesaurus


def reduce_vocab(tokens, similarity=.85, limit=20, sort_order=-1):
    """Find spelling variations of similar words within a list of tokens to reduce token set size

    Lexically sorted in reverse order (unless `reverse=False`), before running through fuzzy-wuzzy
    which results in the longer of identical spellings to be prefered (e.g. "ones" prefered to "one")
    as the key token. Usually you wantThis is usually what you want.

    Arguments:
      tokens (list or set or tuple of str): token strings from which to eliminate similar spellings
      similarity (float): portion of characters that should be unchanged in order to be considered a synonym
        as a fraction of the key token length.
        e.g. `0.85` (which means 85%) allows "hon" to match "on" and "honey", but not "one"

    Returns:
      dict: { 'token': ('similar_token', 'similar_token2', ...), ...}

    Examples:
      >>> tokens = ('on', 'hon', 'honey', 'ones', 'one', 'two', 'three')
      >>> answer = {'hon': ('on', 'honey'),
      ...           'one': ('ones',),
      ...           'three': (),
      ...           'two': ()}
      >>> reduce_vocab(tokens, sort_order=1) == answer
      True
      >>> answer = {'honey': ('hon',),
      ...           'ones': ('on', 'one'),
      ...           'three': (),
      ...           'two': ()}
      >>> reduce_vocab(tokens, sort_order=-1) == answer
      True
      >>> reduce_vocab(tokens, similarity=0.3, limit=2, sort_order=-1) ==  {'ones': ('one',), 'three': ('honey',), 'two': ('on', 'hon')}
      True
      >>> reduce_vocab(tokens, similarity=0.3, limit=3, sort_order=-1) ==  {'ones': (), 'three': ('honey',), 'two': ('on', 'hon', 'one')}
      True

    """
    if 0 <= similarity <= 1:
        similarity *= 100
    if sort_order:
        tokens = set(tokens)
        tokens_sorted = sorted(list(tokens), reverse=bool(sort_order < 0))
    else:
        tokens_sorted = list(tokens)
        tokens = set(tokens)
    # print(tokens)
    thesaurus = {}
    for tok in tokens_sorted:
        try:
            tokens.remove(tok)
        except (KeyError, ValueError):
            continue
        # FIXME: this is slow because the tokens list must be regenerated and reinstantiated with each iteration
        matches = fuzzy.extractBests(tok, list(tokens), score_cutoff=int(similarity), limit=limit)
        if matches:
            thesaurus[tok] = zip(*matches)[0]
        else:
            thesaurus[tok] = ()
        for syn in thesaurus[tok]:
            tokens.discard(syn)
    return thesaurus


def reduce_vocab_by_len(tokens, similarity=.87, limit=20, reverse=True):
    """Find spelling variations of similar words within a list of tokens to reduce token set size

    Sorted by length (longest first unless reverse=False) before running through fuzzy-wuzzy
    which results in longer key tokens.

    Arguments:
      tokens (list or set or tuple of str): token strings from which to eliminate similar spellings

    Returns:
      dict: { 'token': ('similar_token', 'similar_token2', ...), ...}

    Examples:
      >>> tokens = ('on', 'hon', 'honey', 'ones', 'one', 'two', 'three')
      >>> reduce_vocab_by_len(tokens) ==  {'honey': ('on', 'hon', 'one'), 'ones': (), 'three': (), 'two': ()}
      True
    """
    tokens = set(tokens)
    tokens_sorted = zip(*sorted([(len(tok), tok) for tok in tokens], reverse=reverse))[1]
    return reduce_vocab(tokens=tokens_sorted, similarity=similarity, limit=limit, sort_order=0)


def quantify_field_dict(field_dict, precision=None, date_precision=None, cleaner=unicode.strip):
    r"""Convert strings and datetime objects in the values of a dict into float/int/long, if possible

    Arguments:
      field_dict (dict): The dict to have any values (not keys) that are strings "quantified"
      precision (int): Number of digits of precision to enforce
      cleaner: A string cleaner to apply to all string before


    FIXME: this test probably needs to define a time zone for the datetime object
    >>> quantify_field_dict({'_state': object(), 'x': 12345678911131517L, 'y': "\t  Wash Me! \n", 'z': datetime.datetime(1970, 10, 23, 23, 59, 59, 123456)}) == {'x': 12345678911131517L, 'y': u'Wash Me!', 'z': 25574399.123456}
    True
    """
    if cleaner:
        d = clean_field_dict(field_dict, cleaner=cleaner)
    for k, v in d.iteritems():
        if isinstance(d[k], datetime.datetime):
            # seconds since epoch = datetime.datetime(1969,12,31,18,0,0)
            try:
                # around the year 2250, a float conversion of this string will lose 1 microsecond of precision, and around 22500 the loss of precision will be 10 microseconds
                d[k] = float(d[k].strftime('%s.%f'))  # seconds since Jan 1, 1970
                if date_precision is not None and isinstance(d[k], ROUNDABLE_NUMERIC_TYPES):
                    d[k] = round(d[k], date_precision)
                    continue
            except:
                pass
        if not isinstance(d[k], (int, float, long)):
            try:
                d[k] = float(d[k])
            except:
                pass
        if precision is not None and isinstance(d[k], ROUNDABLE_NUMERIC_TYPES):
            d[k] = round(d[k], precision)
        if isinstance(d[k], float) and d[k].is_integer():
            # `int()` will convert to a long, if value overflows an integer type
            # use the original value, `v`, in case it was a long and d[k] is has been truncated by the conversion to float!
            d[k] = int(v)
    return d


def generate_batches(sequence, batch_len=1, allow_partial=True, ignore_errors=True, verbosity=1):
    """Iterate through a sequence (or generator) in batches of length `batch_len`

    http://stackoverflow.com/a/761125/623735
    >>> [batch for batch in generate_batches(range(7), 3)]
    [[0, 1, 2], [3, 4, 5], [6]]
    """
    it = iter(sequence)
    last_value = False
    # An exception will be thrown by `.next()` here and caught in the loop that called this iterator/generator 
    while not last_value:
        batch = []
        for n in xrange(batch_len):
            try:
                batch += (it.next(),)
            except StopIteration:
                last_value = True
                if batch:
                    break
                else:
                    raise StopIteration
            except Exception:
                # 'Error: new-line character seen in unquoted field - do you need to open the file in universal-newline mode?'       
                if verbosity:
                    print_exc()
                if not ignore_errors:
                    raise
        yield batch


def generate_tuple_batches(qs, batch_len=1):
    """Iterate through a queryset in batches of length `batch_len`

    >>> [batch for batch in generate_tuple_batches(range(7), 3)]
    [(0, 1, 2), (3, 4, 5), (6,)]
    """
    num_items, batch = 0, []
    for item in qs:
        if num_items >= batch_len:
            yield tuple(batch)
            num_items = 0
            batch = []
        num_items += 1
        batch += [item]
    if num_items:
        yield tuple(batch)


def sliding_window(seq, n=2):
    """Generate overlapping sliding/rolling windows (of width n) over an iterable
    
    s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...                   

    References:
      http://stackoverflow.com/a/6822773/623735

    Examples:

    >>> list(sliding_window(range(6), 3))  # doctest: +NORMALIZE_WHITESPACE
    [(0, 1, 2),
     (1, 2, 3),
     (2, 3, 4),
     (3, 4, 5)]
    """
    it = iter(seq)
    result = tuple(islice(it, n))
    if len(result) == n:
        yield result    
    for elem in it:
        result = result[1:] + (elem,)
        yield result


def generate_slices(sliceable_set, batch_len=1, length=None, start_batch=0):
    """Iterate through a sequence (or generator) in batches of length `batch_len`

    See Also:
      pug.nlp.djdb.generate_queryset_batches

    References:
      http://stackoverflow.com/a/761125/623735

    Examples:
      >>> [batch for batch in generate_slices(range(7), 3)]
      [(0, 1, 2), (3, 4, 5), (6,)]
      >>> from django.contrib.auth.models import User, Permission
      >>> len(list(generate_slices(User.objects.all(), 2)))       == max(math.ceil(User.objects.count() / 2.), 1)
      True
      >>> len(list(generate_slices(Permission.objects.all(), 2))) == max(math.ceil(Permission.objects.count() / 2.), 1)
      True
    """
    if length is None:
        try:
            length = sliceable_set.count()
        except:
            length = len(sliceable_set)
    length = int(length)

    for i in range(length / batch_len + 1):
        if i < start_batch:
            continue
        start = i * batch_len
        end = min((i + 1) * batch_len, length)
        if start != end:
            yield tuple(sliceable_set[start:end])
    raise StopIteration


COUNT_NAMES = ['count', 'cnt', 'number', 'num', '#', 'frequency', 'probability', 'prob', 'occurences']
def find_count_label(d):
    """Find the member of a set that means "count" or "frequency" or "probability" or "number of occurrences".

    """
    for name in COUNT_NAMES:
        if name in d:
            return name
    for name in COUNT_NAMES:
        if str(name).lower() in d:
            return name


def first_in_seq(seq):
    # lists/sequences
    return next(iter(seq))


def get_key_for_value(dict_obj, value, default=None):
    """
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'you')
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'you', default='Not Found')
    'Not Found'
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'other', default='Not Found')
    'Not Found'
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'want')
    'you'
    >>> get_key_for_value({0: 'what', '': 'ever', 'you': 'want', 'to find': None, 'you': 'too'}, 'what')
    0
    >>> get_key_for_value({0: 'what', '': 'ever', 'you': 'want', 'to find': None, 'you': 'too', ' ': 'want'}, 'want')
    ' '
    """
    for k, v in dict_obj.iteritems():
        if v == value:
            return k
    return default


def list_set(seq):
    """Similar to `list(set(seq))`, but maintains the order of `seq` while eliminating duplicates

    In general list(set(L)) will not have the same order as the original list.
    This is a list(set(L)) function that will preserve the order of L.

    Arguments:
      seq (iterable): list, tuple, or other iterable to be used to produce an ordered `set()`

    Returns:
      iterable: A copy of `seq` but with duplicates removed, and distinct elements in the same order as in `seq`

    Examples:
      >>> list_set([2.7,3,2,2,2,1,1,2,3,4,3,2,42,1])
      [2.7, 3, 2, 1, 4, 42]
      >>> list_set(['Zzz','abc', ('what.', 'ever.'), 0, 0.0, 'Zzz', 0.00, 'ABC'])
      ['Zzz', 'abc', ('what.', 'ever.'), 0, 'ABC']
    """
    new_list = []
    for i in seq:
        if i not in new_list:
            new_list += [i]
    return type(seq)(new_list)


def fuzzy_get(dict_obj, approximate_key, default=None, similarity=0.6, tuple_joiner='|', key_and_value=False, dict_keys=None, ):
    r"""Find the closest matching key in a dictionary and optionally retrieve the associated value

    Notes:
      `dict_obj` must have all string keys!
      Argument order is in reverse order relative to `fuzzywuzzy.process.extractOne()` 
        but in the same order as get(self, key) method on dicts

    Arguments:
      dict_obj (dict): object to run the get method on using the key that is most similar to one within the dict
      approximate_key (str): key to look for a fuzzy match within the dict keys
      default (obj): the value to return if a similar key cannote be found in the `dict_obj`
      similarity (str): fractional similiarity between the approximate_key and the dict key (0.9 means 90% of characters must be identical)
      tuple_joiner (str): Character to use as delimitter/joiner between tuple elements.
        Used to create keys of any tuples to be able to use fuzzywuzzy string matching on it.
      key_and_value (bool): Whether to return both the key and its value (True) or just the value (False). 
        Default is the same behavior as dict.get (i.e. key_and_value=False)
      dict_keys (list of str): if you already have a set of keys to search, this will save this funciton a little time and RAM

    See Also:
      get_similar: Allows nonstring keys and searches object attributes in addition to keys

    Examples:
      >>> fuzzy_get({'seller': 2.7, 'sailor': set('e')}, 'sail')
      set(['e'])
      >>> fuzzy_get({'seller': 2.7, 'sailor': set('e'), 'camera': object()}, 'SLR')
      2.7
      >>> fuzzy_get({'seller': 2.7, 'sailor': set('e'), 'camera': object()}, 'I')
      set(['e'])
      >>> fuzzy_get({'word': tuple('word'), 'noun': tuple('noun')}, 'woh!', similarity=.3, key_and_value=True)
      ('word', ('w', 'o', 'r', 'd'))
      >>> fuzzy_get({'word': tuple('word'), 'noun': tuple('noun')}, 'woh!', similarity=.9, key_and_value=True)
      (None, None)
      >>> fuzzy_get({'word': tuple('word'), 'noun': tuple('noun')}, 'woh!', similarity=.9, default='darn :-()', key_and_value=True)
      (None, 'darn :-()')
    """
    fuzzy_key, value = None, default
    if approximate_key in dict_obj:
        fuzzy_key, value = approximate_key, dict_obj[approximate_key]
    else:
        strkey = unicode(approximate_key)
        if approximate_key and strkey and strkey.strip():
            # print 'no exact match was found for {0} in {1} so preprocessing keys'.format(approximate_key, dict_obj.keys()) 
            if any(isinstance(k, (tuple, list)) for k in dict_obj):
                dict_obj = dict((tuple_joiner.join(str(k2) for k2 in k), v) for (k, v) in dict_obj.iteritems())
                if isinstance(approximate_key, (tuple, list)):
                    strkey = tuple_joiner.join(approximate_key)
            # WARN: fuzzywuzzy requires that the second argument be a list (sets and tuples fail!)
            dict_keys = list(set(dict_keys if dict_keys else dict_obj))
            if strkey in dict_keys:
                fuzzy_key, value = strkey, dict_obj[strkey]
            else:
                strkey = strkey.strip()
                if strkey in dict_keys:
                    fuzzy_key, value = strkey, dict_obj[strkey]
                else:
                    #print 'no exact match was found for {0} in {1} so checking with similarity cutoff of {2}'.format(strkey, dict_keys, similarity) 
                    # WARN: extractBests will return [] if dict_keys is anything other than a list (even sets and tuples fail!)
                    fuzzy_key_scores = fuzzy.extractBests(strkey, dict_keys, score_cutoff=min(max(similarity*100.0 - 1, 0), 100), limit=6)
                    #print strkey, fuzzy_key_scores
                    if fuzzy_key_scores:
                        # print fuzzy_key_scores
                        fuzzy_score_keys = []
                        # add length similarity as part of score
                        for (i, (k, score)) in enumerate(fuzzy_key_scores):
                            fuzzy_score_keys += [(score *  math.sqrt(len(strkey)**2 / float((len(k)**2 + len(strkey)**2) or 1)), k)]
                        # print fuzzy_score_keys
                        fuzzy_score, fuzzy_key = sorted(fuzzy_score_keys)[-1]
                        value = dict_obj[fuzzy_key]
    if key_and_value:
        return fuzzy_key, value
    else:
        return value


def fuzzy_get_tuple(dict_obj, approximate_key, dict_keys=None, key_and_value=False, similarity=0.6, default=None):
    """Find the closest matching key and/or value in a dictionary (must have all string keys!)"""
    return fuzzy_get(dict(('|'.join(str(k2) for k2 in k), v) for (k, v) in dict_obj.iteritems()), 
                     '|'.join(str(k) for k in approximate_key), dict_keys=dict_keys, key_and_value=key_and_value, similarity=similarity, default=default)



def sod_transposed(seq_of_dicts, align=True, fill=True, filler=None):
    """Return sequence (list) of dictionaries, transposed into a dictionary of sequences (lists)
    
    >>> sorted(sod_transposed([{'c': 1, 'cm': u'P'}, {'c': 1, 'ct': 2, 'cm': 6, 'cn': u'MUS'}, {'c': 1, 'cm': u'Q', 'cn': u'ROM'}], filler=0).items())
    [('c', [1, 1, 1]), ('cm', [u'P', 6, u'Q']), ('cn', [0, u'MUS', u'ROM']), ('ct', [0, 2, 0])]
    >>> sorted(sod_transposed(({'c': 1, 'cm': u'P'}, {'c': 1, 'ct': 2, 'cm': 6, 'cn': u'MUS'}, {'c': 1, 'cm': u'Q', 'cn': u'ROM'}), fill=0, align=0).items())
    [('c', [1, 1, 1]), ('cm', [u'P', 6, u'Q']), ('cn', [u'MUS', u'ROM']), ('ct', [2])]
    """
    result = {}
    if isinstance(seq_of_dicts, collections.Mapping):
        seq_of_dicts = [seq_of_dicts]
    it = iter(seq_of_dicts)
    # if you don't need to align and/or fill, then just loop through and return
    if not (align and fill):
        for d in it:
            for k in d:
                result[k] = result.get(k, []) + [d[k]]
        return result
    # need to align and/or fill, so pad as necessary
    for i, d in enumerate(it):
        for k in d:
            result[k] = result.get(k, [filler] * (i * int(align))) + [d[k]]
        for k in result:
            if k not in d:
                result[k] += [filler]
    return result


def joined_seq(seq, sep=None):
    """Join a sequence into a tuple or a concatenated string

    >>> joined_seq(range(3), ', ')
    '0, 1, 2'
    >>> joined_seq([1, 2, 3])
    (1, 2, 3)
    """
    joined_seq = tuple(seq)
    if isinstance(sep, basestring):
        joined_seq = sep.join(str(item) for item in joined_seq)
    return joined_seq


def consolidate_stats(dict_of_seqs, stats_key=None, sep=','):
    """Join (stringify and concatenate) keys (table fields) in a dict (table) of sequences (columns)

    >>> consolidate_stats(dict([('c', [1, 1, 1]), ('cm', [u'P', 6, u'Q']), ('cn', [0, u'MUS', u'ROM']), ('ct', [0, 2, 0])]), stats_key='c')
    [{'P,0,0': 1}, {'6,MUS,2': 1}, {'Q,ROM,0': 1}]
    >>> consolidate_stats([{'c': 1, 'cm': 'P', 'cn': 0, 'ct': 0}, {'c': 1, 'cm': 6, 'cn': 'MUS', 'ct': 2}, {'c': 1, 'cm': 'Q', 'cn': 'ROM', 'ct': 0}], stats_key='c')
    [{'P,0,0': 1}, {'6,MUS,2': 1}, {'Q,ROM,0': 1}]
    """
    if isinstance(dict_of_seqs, dict):
        stats = dict_of_seqs[stats_key]
        keys = joined_seq(sorted([k for k in dict_of_seqs if k is not stats_key]), sep=None)
        joined_key = joined_seq(keys, sep=sep)
        result = {stats_key: [], joined_key: []}
        for i, stat in enumerate(stats):
            result[stats_key] += [stat]
            result[joined_key] += [joined_seq((dict_of_seqs[k][i] for k in keys if k is not stats_key), sep)]
        return list({k: result[stats_key][i]} for i, k in enumerate(result[joined_key]))
    return [{joined_seq((d[k] for k in sorted(d) if k is not stats_key), sep): d[stats_key]} for d in dict_of_seqs]


def dos_from_table(table, header=None):
    """Produce dictionary of sequences from sequence of sequences, optionally with a header "row".

    >>> dos_from_table([['hello', 'world'], [1, 2], [3,4]]) == {'hello': [1, 3], 'world': [2, 4]}
    True
    """
    start_row = 0
    if not table:
        return table
    if not header:
        header = table[0]
        start_row = 1
    header_list = header
    if header and isinstance(header, basestring):
        header_list = header.split('\t')
        if len(header_list)!=len(table[0]):
            header_list = header.split(',')
        if len(header_list)!=len(table[0]):
            header_list = header.split(' ')
    ans = {}
    for i, k in enumerate(header):
        ans[k] = [row[i] for row in table[start_row:]]
    return ans


def transposed_lists(list_of_lists, default=None):
    """Like `numpy.transposed`, but allows uneven row lengths

    Uneven lengths will affect the order of the elements in the rows of the transposed lists

    >>> transposed_lists([[1, 2], [3, 4, 5], [6]])
    [[1, 3, 6], [2, 4], [5]]
    >>> transposed_lists(transposed_lists([[], [1, 2, 3], [4]]))
    [[1, 2, 3], [4]]
    >>> l = transposed_lists([range(4),[4,5]])
    >>> l
    [[0, 4], [1, 5], [2], [3]]
    >>> transposed_lists(l)
    [[0, 1, 2, 3], [4, 5]]
    """
    if default is None or default is [] or default is tuple():
        default = []
    elif default is 'None':
        default = [None]
    else:
        default = [default]
    
    N = len(list_of_lists)
    Ms = [len(row) for row in list_of_lists]
    M = max(Ms)
    ans = []
    for j in range(M):
        ans += [[]]
        for i in range(N):
            if j < Ms[i]:
                ans[-1] += [list_of_lists[i][j]]
            else:
                ans[-1] += list(default)
    return ans


def transposed_matrix(matrix, filler=None, row_type=list, matrix_type=list, value_type=None):
    """Like numpy.transposed, evens up row (list) lengths that aren't uniform, filling with None.

    Also, makes all elements a uniform type (default=type(matrix[0][0])), 
    except for filler elements.

    TODO: add feature to delete None's at the end of rows so that transpose(transpose(LOL)) = LOL

    >>> transposed_matrix([[1, 2], [3, 4, 5], [6]])
    [[1, 3, 6], [2, 4, None], [None, 5, None]]
    >>> transposed_matrix(transposed_matrix([[1, 2], [3, 4, 5], [6]]))
    [[1, 2, None], [3, 4, 5], [6, None, None]]
    >>> transposed_matrix([[], [1, 2, 3], [4]])  # empty first row forces default value type (float)
    [[None, 1.0, 4.0], [None, 2.0, None], [None, 3.0, None]]
    >>> transposed_matrix(transposed_matrix([[], [1, 2, 3], [4]]))
    [[None, None, None], [1.0, 2.0, 3.0], [4.0, None, None]]
    >>> l = transposed_matrix([range(4),[4,5]])
    >>> l
    [[0, 4], [1, 5], [2, None], [3, None]]
    >>> transposed_matrix(l)
    [[0, 1, 2, 3], [4, 5, None, None]]
    >>> transposed_matrix([[1,2],[1],[1,2,3]])
    [[1, 1, 1], [2, None, 2], [None, None, 3]]
    """

    matrix_type = matrix_type or type(matrix)
    # matrix = matrix_type(matrix)

    try:
        row_type = row_type or type(matrix[0])
    except:
        pass
    if not row_type or row_type == type(None):
        row_type = list

    try:
        value_type = value_type or type(matrix[0][0]) or float
    except:
        pass
    if not value_type or value_type == type(None):
        value_type = float

    #print matrix_type, row_type, value_type

    # original matrix is NxM, new matrix will be MxN
    N = len(matrix)
    Ms = [len(row) for row in matrix]
    M = 0 if not Ms else max(Ms)

    ans = []
    # for each row in the new matrix (column in old matrix)
    for j in range(M):
        # add a row full of copies the `fill` value up to the maximum width required
        ans += [row_type([filler] * N)]
        for i in range(N):
            try:
                ans[j][i] = value_type(matrix[i][j])
            except IndexError:
                ans[j][i] = filler
            except TypeError:
                ans[j][i] = filler

    try:
        if isinstance(ans[0], row_type):
            return matrix_type(ans)
    except:
        pass
    return matrix_type([row_type(row) for row in ans])


def hist_from_counts(counts, normalize=False, cumulative=False, to_str=False, sep=',', min_bin=None, max_bin=None):
    """Compute an emprical histogram, PMF or CDF in a list of lists

    TESTME: compare results to hist_from_values_list and hist_from_float_values_list
    """
    counters = [dict((i, c)for i, c in enumerate(counts))]


    intkeys_list = [[c for c in counts_dict if (isinstance(c, int) or (isinstance(c, float) and int(c) == c))] for counts_dict in counters]
    min_bin, max_bin = min_bin or 0, max_bin or len(counts) - 1 

    histograms = []
    for intkeys, counts in zip(intkeys_list, counters):
        histograms += [OrderedDict()]
        if not intkeys:
            continue
        if normalize:
            N = sum(counts[c] for c in intkeys)
            for c in intkeys:
                counts[c] = float(counts[c]) / N
        if cumulative:
            for i in xrange(min_bin, max_bin + 1):
                histograms[-1][i] = counts.get(i, 0) + histograms[-1].get(i-1, 0)
        else:
            for i in xrange(min_bin, max_bin + 1):
                histograms[-1][i] = counts.get(i, 0)
    if not histograms:
        histograms = [OrderedDict()]

    # fill in the zero counts between the integer bins of the histogram
    aligned_histograms = []

    for i in range(min_bin, max_bin + 1):
        aligned_histograms += [tuple([i] + [hist.get(i, 0) for hist in histograms])]

    if to_str:
        # FIXME: add header row
        return str_from_table(aligned_histograms, sep=sep, max_rows=365*2+1)

    return aligned_histograms


def hist_from_values_list(values_list, fillers=(None,), normalize=False, cumulative=False, to_str=False, sep=',', min_bin=None, max_bin=None):
    """Compute an emprical histogram, PMF or CDF in a list of lists or a csv string

    Only works for discrete (integer) values (doesn't bin real values).
    `fillers`: list or tuple of values to ignore in computing the histogram

    >>> hist_from_values_list([1,1,2,1,1,1,2,3,2,4,4,5,7,7,9])  # doctest: +NORMALIZE_WHITESPACE
    [(1, 5), (2, 3), (3, 1), (4, 2), (5, 1), (6, 0), (7, 2), (8, 0), (9, 1)]
    >>> hist_from_values_list([(1,9),(1,8),(2,),(1,),(1,4),(2,5),(3,3),(5,0),(2,2)])  # doctest: +NORMALIZE_WHITESPACE
    [[(1, 4), (2, 3), (3, 1), (4, 0), (5, 1)], [(0, 1), (1, 0), (2, 1), (3, 1), (4, 1), (5, 1), (6, 0), (7, 0), (8, 1), (9, 1)]]
    >>> hist_from_values_list(transposed_matrix([(8,),(1,3,5),(2,),(3,4,5,8)]))  # doctest: +NORMALIZE_WHITESPACE
    [[(8, 1)], [(1, 1), (2, 0), (3, 1), (4, 0), (5, 1)], [(2, 1)], [(3, 1), (4, 1), (5, 1), (6, 0), (7, 0), (8, 1)]]
    """
    value_types = tuple([int, float] + [type(filler) for filler in fillers])

    if all(isinstance(value, value_types) for value in values_list):
        # ignore all fillers and convert all floats to ints when doing counting
        counters = [collections.Counter(int(value) for value in values_list if isinstance(value, (int, float)))]
    elif all(len(row)==1 for row in values_list) and all(isinstance(row[0], value_types) for row in values_list):
        return hist_from_values_list([values[0] for values in values_list], fillers=fillers, normalize=normalize, cumulative=cumulative, to_str=to_str, sep=sep, min_bin=min_bin, max_bin=max_bin)
    else:  # assume it's a row-wise table (list of rows)
        return [
            hist_from_values_list(col, fillers=fillers, normalize=normalize, cumulative=cumulative, to_str=to_str, sep=sep, min_bin=min_bin, max_bin=max_bin)
            for col in transposed_matrix(values_list)
            ]

    if not values_list:
        return []

    intkeys_list = [[c for c in counts if (isinstance(c, int) or (isinstance(c, float) and int(c) == c))] for counts in counters]
    try:
        min_bin = int(min_bin)
    except:
        min_bin = min(min(intkeys) for intkeys in intkeys_list)
    try:
        max_bin = int(max_bin)
    except:
        max_bin = max(max(intkeys) for intkeys in intkeys_list)

    # FIXME: this looks slow and hazardous (like it's ignore min/max bin):
    min_bin = max(min_bin, min((min(intkeys) if intkeys else 0) for intkeys in intkeys_list))  # TODO: reuse min(intkeys)
    max_bin = min(max_bin, max((max(intkeys) if intkeys else 0) for intkeys in intkeys_list))  # TODO: reuse max(intkeys)

    histograms = []
    for intkeys, counts in zip(intkeys_list, counters):
        histograms += [OrderedDict()]
        if not intkeys:
            continue
        if normalize:
            N = sum(counts[c] for c in intkeys)
            for c in intkeys:
                counts[c] = float(counts[c]) / N
        if cumulative:
            for i in xrange(min_bin, max_bin + 1):
                histograms[-1][i] = counts.get(i, 0) + histograms[-1].get(i-1, 0)
        else:
            for i in xrange(min_bin, max_bin + 1):
                histograms[-1][i] = counts.get(i, 0)
    if not histograms:
        histograms = [OrderedDict()]

    # fill in the zero counts between the integer bins of the histogram
    aligned_histograms = []

    for i in range(min_bin, max_bin + 1):
        aligned_histograms += [tuple([i] + [hist.get(i, 0) for hist in histograms])]

    if to_str:
        # FIXME: add header row
        return str_from_table(aligned_histograms, sep=sep, max_rows=365*2+1)

    return aligned_histograms


def get_similar(obj, labels, default=None, min_similarity=0.5):
    """Similar to fuzzy_get, but allows non-string keys and a list of possible keys

    Searches attributes in addition to keys and indexes.

    See Also:
        `fuzzy_get`
    """
    raise NotImplementedError("Unfinished implementation, needs to be incorporated into fuzzy_get where a list of scores and keywords is sorted.")
    labels = listify(labels)
    not_found = lambda: 0
    min_score = int(min_similarity * 100)
    for similarity_score in [100, 95, 90, 80, 70, 50, 30, 10, 5, 0]:
        if similarity_score <= min_score:
            similarity_score = min_score
        for label in labels:
            try:
                result = obj.get(label, not_found)
            except AttributeError:
                try:
                    result = obj.__getitem__(label)
                except (IndexError, TypeError):
                    result = not_found
            if not result is not_found:
                return result
        if similarity_score == min_score:
            if not result is not_found:
                return result


def update_dict(d, u, depth=-1, take_new=True, default_mapping_type=dict, prefer_update_type=False, copy=False):
    """
    Recursively merge (union or update) dict-like objects (collections.Mapping) to the specified depth.

    >>> update_dict({'k1': {'k2': 2}}, {'k1': {'k2': {'k3': 3}}, 'k4': 4})
    {'k1': {'k2': {'k3': 3}}, 'k4': 4}
    >>> update_dict(OrderedDict([('k1', OrderedDict([('k2', 2)]))]), {'k1': {'k2': {'k3': 3}}, 'k4': 4})
    OrderedDict([('k1', OrderedDict([('k2', {'k3': 3})])), ('k4', 4)])
    >>> update_dict(OrderedDict([('k1', dict([('k2', 2)]))]), {'k1': {'k2': {'k3': 3}}, 'k4': 4})
    OrderedDict([('k1', {'k2': {'k3': 3}}), ('k4', 4)])
    >>> orig = {'orig_key': 'orig_value'}
    >>> updated = update_dict(orig, {'new_key': 'new_value'}, copy=True)
    >>> updated == orig
    False
    >>> updated2 = update_dict(orig, {'new_key2': 'new_value2'})
    >>> updated2 == orig
    True
    >>> update_dict({'k1': {'k2': {'k3': 3}}, 'k4': 4}, {'k1': {'k2': 2}}, depth=1, take_new=False)
    {'k1': {'k2': 2}, 'k4': 4}
    >>> # FIXME: this result is unexpected the same as for `take_new=False`
    >>> update_dict({'k1': {'k2': {'k3': 3}}, 'k4': 4}, {'k1': {'k2': 2}}, depth=1, take_new=True)
    {'k1': {'k2': 2}, 'k4': 4}
    """
    orig_mapping_type = type(d)
    if prefer_update_type and isinstance(u, collections.Mapping):
        dictish = type(u)
    elif isinstance(d, collections.Mapping):
        dictish = orig_mapping_type
    else:
        dictish = default_mapping_type
    if copy:
        d = dictish(d)
    for k, v in u.iteritems():
        if isinstance(d, collections.Mapping):
            if isinstance(v, collections.Mapping) and not depth == 0:
                r = update_dict(d.get(k, dictish()), v, depth=max(depth - 1, -1), copy=copy)
                d[k] = r
            elif take_new:
                d[k] = u[k]
        elif take_new:
            d = dictish([(k, u[k])])
    return d


def mapped_transposed_lists(lists, default=None):
    """
    Swap rows and columns in list of lists with different length rows/columns

    Pattern from
    http://code.activestate.com/recipes/410687-transposing-a-list-of-lists-with-different-lengths/
    Replaces any zeros or Nones with default value.

    Examples:
    >>> l = mapped_transposed_lists([range(4),[4,5]],None)
    >>> l
    [[0, 4], [1, 5], [2, None], [3, None]]
    >>> mapped_transposed_lists(l)
    [[0, 1, 2, 3], [4, 5, None, None]]
    """
    if not lists:
        return []
    return map(lambda *row: [el if isinstance(el, (float, int)) else default for el in row], *lists)


def make_name(s, camel=None, lower=None, space='_', remove_prefix=None, language='python', string_type=unicode):
    """Process a string to produce a valid python variable/class/type name

    Arguments:
      space (str): string to substitute for spaces ('' to delete all whitespace)
      camel (bool): whether to camel-case names, Django Model Name style (first letter capitalized)
      lower (bool): whether to lowercase all strings 
      language (str): case-insensitive language identifier (to deterimine allowable identifier characters)
        e.g. 'Python', 'Python2', 'Python3', 'Javascript', 'ECMA'

    Examples:
      Generate Django model names out of file names
      >>> make_name('women in IT.csv', camel=True)
      u'WomenInItCsv'
      
      Generate Django field names out of CSV header strings
      >>> make_name('ID Number (9-digits)')
      u'id_number_9_digits_'
      >>> make_name("PD / SZ")
      u'pd_sz'

      Generate Javscript object attribute names from CSV header strings
      >>> make_name(u'pi (\u03C0)', space = '', language='javascript')
      u'pi\u03c0'
      >>> make_name(u'pi (\u03C0)', space = '', language='javascript')
      u'pi\u03c0'
    """
    if camel is None and lower is None:
        lower = True
    if not s:
        return None
    ecma_languages = ['ecma', 'javasc']
    unicode_languages = ecma_languages
    language = language or 'python'
    language = language.lower().strip()[:6]
    string_type = string_type or str
    if language in unicode_languages:
        string_type = unicode
    s = string_type(s)  # TODO: encode in ASCII, UTF-8, or the charset used for this file!
    if remove_prefix and s.startswith(remove_prefix):
        s = s[len(remove_prefix):]
    if camel:
        if space and space == '_':
            space = ''
        if any(c in ' \t\n\r' + string.punctuation for c in s) or s.lower() == s:
            if lower:
                s = s.lower()
            s = s.title()
    elif lower:
        s = s.lower()
    # TODO: add language Regexes to filter characters appropriately for python or javascript
    space_escape = '\\' if space and space not in ' _' else ''
    if not language in ecma_languages:
        invalid_char_regex = re.compile('[^a-zA-Z0-9' + space_escape + space +']+')
    else:
        # FIXME: Unicode categories and properties only works in Perl Regexes!
        invalid_char_regex = re.compile('[\W' + space_escape + space +']+', re.UNICODE)
    if space is not None:
        # get rid of all invalid characters, substitting the space-filler for them all
        s = invalid_char_regex.sub(space, s)
        # get rid of duplicate space-filler characters
        if space:
            s = re.sub('[' + space_escape + space + ']{2,}', space, s)
    return s
make_name.DJANGO_FIELD = {'camel': False, 'lower': True, 'space': '_'}
make_name.DJANGO_MODEL = {'camel': True, 'lower': False, 'space': '', 'remove_prefix': 'models'}


def make_filename(s, space=None, language='msdos', strict=False, max_len=None, repeats=1024):
    r"""Process string to remove any characters not allowed by the language specified (default: MSDOS)

    In addition, optionally replace spaces with the indicated "space" character
    (to make the path useful in a copy-paste without quoting).

    Uses the following regular expression to substitute spaces for invalid characters:

        re.sub(r'[ :\\/?*&"<>|~`!]{1}', space, s)

    >>> make_filename(r'Whatever crazy &s $h!7 n*m3 ~\/ou/ can come up. with.`txt`!', strict=False)
    'Whatever-crazy-s-$h-7-n-m3-ou-can-come-up.-with.-txt-'
    >>> make_filename(r'Whatever crazy &s $h!7 n*m3 ~\/ou/ can come up. with.`txt`!', strict=False, repeats=1)
    'Whatever-crazy--s-$h-7-n-m3----ou--can-come-up.-with.-txt--'
    >>> make_filename(r'Whatever crazy &s $h!7 n*m3 ~\/ou/ can come up. with.`txt`!', repeats=1)
    'Whatever-crazy--s-$h-7-n-m3----ou--can-come-up.-with.-txt--'
    >>> make_filename(r'Whatever crazy &s $h!7 n*m3 ~\/ou/ can come up. with.`txt`!')
    'Whatever-crazy-s-$h-7-n-m3-ou-can-come-up.-with.-txt-'
    >>> make_filename(r'Whatever crazy &s $h!7 n*m3 ~\/ou/ can come up. with.`txt`!', strict=True, repeats=1)
    u'Whatever_crazy_s_h_7_n_m3_ou_can_come_up_with_txt_'
    >>> make_filename(r'Whatever crazy &s $h!7 n*m3 ~\/ou/ can come up. with.`txt`!', strict=True, repeats=1, max_len=14)
    u'Whatever_crazy'
    >>> make_filename(r'Whatever crazy &s $h!7 n*m3 ~\/ou/ can come up. with.`txt`!', max_len=14)
    'Whatever-crazy'
    """
    filename = None
    if strict or language.lower().strip() in ('strict', 'variable', 'expression', 'python'):
        if space == None:
            space = '_'
        elif not space:
            space = ''
        filename = make_name(s, space=space, lower=False)
    else:
        if space == None:
            space = '-'
        elif not space:
            space = ''
    if not filename:
        if language.lower().strip() in ('posix', 'unix', 'linux', 'centos', 'ubuntu', 'fedora', 'redhat', 'rhel', 'debian', 'deb'):
            filename = re.sub(r'[^0-9A-Za-z._-]' + '\{1,{0}\}'.format(repeats), space, s)
        else:
            filename = re.sub(r'[ :\\/?*&"<>|~`!]{' + ('1,{0}'.format(repeats)) + r'}', space, s)
    if max_len and int(max_len) > 0 and filename:
        return filename[:int(max_len)]
    else:
        return filename


def update_file_ext(filename, ext='txt', sep='.'):
    """Force the file or path str to end with the indicated extension

    Note: a dot (".") is assumed to delimit the extension

    >>> update_file_ext('/home/hobs/extremofile', 'bac')
    '/home/hobs/extremofile.bac'
    >>> update_file_ext('/home/hobs/piano.file/', 'music')
    '/home/hobs/piano.file/.music'
    >>> update_file_ext('/home/ninja.hobs/Anglofile', '.uk')
    '/home/ninja.hobs/Anglofile.uk'
    >>> update_file_ext('/home/ninja-corsi/audio', 'file', sep='-')
    '/home/ninja-corsi/audio-file'
    """ 
    path, filename = os.path.split(filename)

    if ext and ext[0] == sep:
        ext = ext[1:]
    return os.path.join(path, sep.join(filename.split(sep)[:-1 if filename.count(sep) > 1 else 1] + [ext]))


def tryconvert(value, desired_types=SCALAR_TYPES, default=None, empty='', strip=True):
    """
    Convert value to one of the desired_types specified (in order of preference) without raising an exception.

    If value is empty is a string and Falsey, then return the `empty` value specified.
    If value can't be converted to any of the desired_types requested, then return the `default` value specified.

    >>> tryconvert('MILLEN2000', desired_types=float, default='GENX')
    'GENX'
    >>> tryconvert('1.23', desired_types=[int,float], default='default')
    1.23
    >>> tryconvert('-1.0', desired_types=[int,float])  # assumes you want a float if you have a trailing .0 in a str
    -1.0
    >>> tryconvert(-1.0, desired_types=[int,float])  # assumes you want an int if int type listed first
    -1
    >>> repr(tryconvert('1+1', desired_types=[int,float]))
    'None'
    """
    if value in tryconvert.EMPTY:
        if isinstance(value, basestring):
            return type(value)(empty)
        return empty
    if isinstance(value, basestring):
        # there may not be any "empty" strings that won't be caught by the `is ''` check above, but just in case
        if not value:
            return type(value)(empty)
        if strip:
            value = value.strip()
    if isinstance(desired_types, type):
        desired_types = (desired_types,)
    if desired_types is not None and len(desired_types) == 0:
        desired_types = tryconvert.SCALAR
    if len(desired_types):
        if isinstance(desired_types, (list, tuple)) and len(desired_types) and isinstance(desired_types[0], (list, tuple)):
            desired_types = desired_types[0]
        elif isinstance(desired_types, type):
            desired_types = [desired_types]
    for t in desired_types:
        try:
            return t(value)
        except (ValueError, TypeError):
            continue
        # if any other weird exception happens then need to get out of here
        return default
    # if no conversions happened successfully then return the default value requested
    return default
tryconvert.EMPTY = ('', None, float('nan'))
tryconvert.SCALAR = SCALAR_TYPES

import codecs

def transcode(infile, outfile=None, incoding="shift-jis", outcoding="utf-8"):
    if not outfile:
        outfile = os.path.basename(infile) + '.utf8'
    with codecs.open(infile, "rb", incoding) as fpin:
        with codecs.open(outfile, "wb", outcoding) as fpout:
            fpout.write(fpin.read())


def read_csv(path, ext='.csv', verbose=False, format=None, delete_empty_keys=False,
             fieldnames=[], rowlimit=100000000, numbers=False, normalize_names=True, unique_names=True):
    """
    Read a csv file from the specified path, return a dict of lists or list of lists (according to `format`)

    filename: a directory or list of file paths
    numbers: whether to attempt to convert strings in csv to numbers
    """
    if not path:
        return

    if format:
        format = format[0].lower()
    recs = []
    # see http://stackoverflow.com/a/4169762/623735 before trying 'rU'
    with open(path, 'rUb') as fpin:  # U = universal EOL reader, b = binary
        # if fieldnames not specified then assume that first row of csv contains headings
        csvr = csv.reader(fpin, dialect=csv.excel)
        if not fieldnames:
            while not fieldnames or not any(fieldnames):
                fieldnames = csvr.next()
            if verbose:
                logger.info('Column Labels: ' + repr(fieldnames))
        if unique_names:
            norm_names = OrderedDict([(fldnm, fldnm) for fldnm in fieldnames])
        else:
            norm_names = OrderedDict([(num, fldnm) for num, fldnm in enumerate(fieldnames)])
        if normalize_names:
            norm_names = OrderedDict([(num, make_name(fldnm, **make_name.DJANGO_FIELD)) for num, fldnm in enumerate(fieldnames)])
            # required for django-formatted json files
            model_name = make_name(path, **make_name.DJANGO_MODEL)
        if format in ('c',):  # columnwise dict of lists
            recs = OrderedDict((norm_name, []) for norm_name in norm_names.values())
        if verbose:
            logger.info('Field Names: ' + repr(norm_names if normalize_names else fieldnames))
        rownum = 0
        eof = False
        pbar = None
        file_len = os.fstat(fpin.fileno()).st_size
        if verbose:
            pbar = ProgressBar(maxval=file_len)
            pbar.start()
        while csvr and rownum < rowlimit and not eof:
            if pbar:
                pbar.update(fpin.tell())
            rownum += 1
            row = []
            row_dict = OrderedDict()
            # skips rows with all empty strings as values,
            while not row or not any(len(x) for x in row):
                try:
                    row = csvr.next()
                    if verbose > 1:
                        logger.info('  row content: ' + repr(row))
                except StopIteration:
                    eof = True
                    break
            if eof:
                break
            if numbers:
                # try to convert the type to a numerical scalar type (int, float etc)
                row = [tryconvert(v, empty=None, default=v) for v in row]
            if row:
                N = min(max(len(row), 0), len(norm_names))
                row_dict = OrderedDict(((field_name, field_value) for field_name, field_value in zip(list(norm_names.values() if unique_names else norm_names)[:N], row[:N]) if (str(field_name).strip() or delete_empty_keys is False)))
                if format in ('d', 'j'):  # django json format
                    recs += [{"pk": rownum, "model": model_name, "fields": row_dict}]
                elif format in ('v',):  # list of values format
                    # use the ordered fieldnames attribute to keep the columns in order
                    recs += [[value for field_name, value in row_dict.iteritems() if (field_name.strip() or delete_empty_keys is False)]]
                elif format in ('c',):  # columnwise dict of lists
                    for field_name in row_dict:
                        recs[field_name] += [row_dict[field_name]]
                else:
                    recs += [row_dict]
        if file_len > fpin.tell():
            logger.info("Only %d of %d bytes were read." % (fpin.tell(), file_len))
        if pbar:
            pbar.finish()
    if not unique_names:
        return recs, norm_names
    return recs


# date and datetime separators
COLUMN_SEP = re.compile(r'[,/;]')


def make_dataframe(prices, num_prices=1, columns=('portfolio',)):
    """Convert a file, list of strings, or list of tuples into a Pandas DataFrame

    Arguments:
      num_prices (int): if not null, the number of columns (from right) that contain numeric values
    """
    if isinstance(prices, pd.Series):
        return pd.DataFrame(prices)
    if isinstance(prices, pd.DataFrame):
        return prices
    if isinstance(prices, basestring) and os.path.isfile(prices):
        prices = open(prices, 'rU')
    if isinstance(prices, file):
        values = []
        # FIXME: what if it's not a CSV but a TSV or PSV
        csvreader = csv.reader(prices, dialect='excel', quoting=csv.QUOTE_MINIMAL)
        for row in csvreader:
            # print row
            values += [row]
        prices.close()
        prices = values
    for row0 in prices:
        if isinstance(row, basestring):
            # FIXME: this looks hazardous, rebuilding the sequence you're iterating through
            prices = [COLUMN_SEP.split(row) for row in prices]
        break
    # print prices
    index = []
    if isinstance(prices[0][0], (datetime.date, datetime.datetime, datetime.time)):
        index = [prices[0] for row in prices]
        for i, row in prices:
            prices[i] = row[1:]
    # try to convert all strings to something numerical:
    elif any(any(isinstance(value, basestring) for value in row) for row in prices):
        #print '-'*80
        for i, row in enumerate(prices):
            #print i, row
            for j, value in enumerate(row):
                s = unicode(value).strip().strip('"').strip("'")
                #print i, j, s
                try:
                    prices[i][j] = int(s)
                    # print prices[i][j]
                except:
                    try:
                        prices[i][j] = float(s)
                    except:
                        # print 'FAIL'
                        try:
                            # this is a probably a bit too forceful
                            prices[i][j] = parse_date(s)
                        except:
                            pass
    # print prices
    width = max(len(row) for row in prices)
    datetime_width = width - num_prices
    if not index and isinstance(prices[0], (tuple, list)) and num_prices:
        # print '~'*80
        new_prices = []
        try:
            for i, row in enumerate(prices):
                # print i, row
                index += [datetime.datetime(*[int(i) for i in row[:datetime_width]])
                          + datetime.timedelta(hours=16)]
                new_prices += [row[datetime_width:]]
                # print prices[-1]
        except:
            for i, row in enumerate(prices):
                index += [row[0]]
                new_prices += [row[1:]]
        prices = new_prices or prices
    # print index
    # TODO: label the columns somehow (if first row is a bunch of strings/header)
    if len(index) == len(prices):
        df = pd.DataFrame(prices, index=index, columns=columns)
    else:
        df = pd.DataFrame(prices)
    return df


def column_name_to_date(name):
    """
    TODO: should probably assume a 2000 epoch for 2-digit dates

    >>> column_name_to_date('10-Apr')
    datetime.date(10, 4, 1)
    >>> column_name_to_date('10_2011')
    datetime.date(2011, 10, 1)
    >>> column_name_to_date('apr_10')
    datetime.date(10, 4, 1)
    """
    month_nums = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
    year_month = re.split(r'[^0-9a-zA-Z]{1}', name)
    try:
        year = int(year_month[0])
        month = year_month[1]
    except:
        year = int(year_month[1])
        month = year_month[0]
    month = month_nums.get(str(month).lower().title(), None)
    if 0 <= year <= 2100 and 1 <= month <= 12:
        return datetime.date(year, month, 1)
    try:
        year = int(year_month[1])
        month = int(year_month[0])
    except:
        year. month = 0, 0
    if 0 <= year <= 2100 and 1 <= month <= 12:
        return datetime.date(year, month, 1)
    try:
        month = int(year_month[1])
        year = int(year_month[0])
    except:
        year. month = 0, 0
    if 0 <= year <= 2100 and 1 <= month <= 12:
        return datetime.date(year, month, 1)



def first_digits(s, default=0):
    """Return the fist (left-hand) digits in a string as a single integer, ignoring sign (+/-).
    >>> first_digits('+123.456')
    123
    """
    s = re.split(r'[^0-9]+', str(s).strip().lstrip('+-' + chars.whitespace))
    if len(s) and len(s[0]):
        return int(s[0])
    return default


def int_pair(s, default=(0, None)):
    """Return the digits to either side of a single non-digit character as a 2-tuple of integers

    >>> int_pair('90210-007')
    (90210, 7)
    >>> int_pair('04321.0123')
    (4321, 123)
    """
    s = re.split(r'[^0-9]+', str(s).strip())
    if len(s) and len(s[0]):
        if len(s) > 1 and len(s[1]):
            return (int(s[0]), int(s[1]))
        return (int(s[0]), default[1])
    return default


def make_us_postal_code(s, allowed_lengths=(), allowed_digits=()):
    """
    >>> make_us_postal_code(1234)
    '01234'
    >>> make_us_postal_code(507.6009)
    '507'
    >>> make_us_postal_code(90210.0)
    '90210'
    >>> make_us_postal_code(39567.7226)
    '39567-7226'
    >>> make_us_postal_code(39567.7226)
    '39567-7226'
    """
    allowed_lengths = allowed_lengths or tuple(N if N < 6 else N + 1 for N in allowed_digits)
    allowed_lengths = allowed_lengths or (2, 3, 5, 10)
    ints = int_pair(s)
    z = str(ints[0]) if ints[0] else ''
    z4 = '-' + str(ints[1]) if ints[1] else ''
    if len(z) == 4:
        z = '0' + z
    if len(z + z4) in allowed_lengths:
        return z + z4
    elif len(z) in (min(l, 5) for l in allowed_lengths):
        return z
    return ''

# TODO: create and check MYSQL_MAX_FLOAT constant
def make_float(s, default='', ignore_commas=True):
    r"""Coerce a string into a float

    >>> make_float('12,345')
    12345.0
    >>> make_float('12.345')
    12.345
    >>> make_float('1+2')
    3.0
    >>> make_float('+42.0')
    42.0
    >>> make_float('\r\n-42?\r\n')
    -42.0
    >>> make_float('$42.42')
    42.42
    >>> make_float('B-52')
    -52.0
    >>> make_float('1.2 x 10^34')
    1.2e+34
    >>> make_float(float('nan'))
    nan
    >>> make_float(float('-INF'))
    -inf
    """
    if ignore_commas and isinstance(s, basestring):
        s = s.replace(',', '')
    try:
        return float(s)
    except:
        try:
            return float(str(s))
        except ValueError:
            try:
                return float(normalize_scientific_notation(str(s), ignore_commas))
            except ValueError:
                try:
                    return float(first_digits(s))
                except ValueError:
                    return default


# TODO: create and check MYSQL_MAX_FLOAT constant
def make_int(s, default='', ignore_commas=True):
    r"""Coerce a string into an integer (long ints will fail)

    TODO:
    - Ignore dashes and other punctuation within a long string of digits,
       like a telephone number, partnumber, datecode or serial number.
    - Use the Decimal type to allow infinite precision
    - Use regexes to be more robust

    >>> make_int('12345')
    12345
    >>> make_int('0000012345000       ')
    12345000
    >>> make_int(' \t\n123,450,00\n')
    12345000
    """
    if ignore_commas and isinstance(s, basestring):
        s = s.replace(',', '')
    try:
        return int(s)
    except:
        pass
    try:
        return int(re.split(str(s), '[^-0-9,.Ee]')[0])
    except ValueError:
        try:
            return int(float(normalize_scientific_notation(str(s), ignore_commas)))
        except (ValueError, TypeError):
            try:
                return int(first_digits(s))
            except (ValueError, TypeError):
                return default


# FIXME: use locale and/or check that they occur ever 3 digits (1000's places) to decide whether to ignore commas
def normalize_scientific_notation(s, ignore_commas=True, verbosity=1):
    """Produce a string convertable with float(s), if possible, fixing some common scientific notations

    Deletes commas and allows addition.
    >>> normalize_scientific_notation(' -123 x 10^-45 ')
    '-123e-45'
    >>> normalize_scientific_notation(' -1+1,234 x 10^-5,678 ')
    '1233e-5678'
    >>> normalize_scientific_notation('$42.42')
    '42.42'
    """
    s = s.lstrip(chars.not_digits_nor_sign)
    s = s.rstrip(chars.not_digits)
    #print s
    # TODO: substitute ** for ^ and just eval the expression rather than insisting on a base-10 representation
    num_strings = RE.scientific_notation_exponent.split(s, maxsplit=2)
    #print num_strings
    # get rid of commas
    s = RE.re.sub(r"[^.0-9-+" + "," * int(not ignore_commas) + r"]+", '', num_strings[0])
    #print s
    # if this value gets so large that it requires an exponential notation, this will break the conversion
    if not s:
        return None
    try:
        s = str(eval(s.strip().lstrip('0')))
    except:
        if verbosity > 1:
            print 'Unable to evaluate %s' % repr(s)
        try:
            s = str(float(s))
        except:
            print 'Unable to float %s' % repr(s)
            s = ''
    #print s
    if len(num_strings) > 1:
        if not s:
            s = '1'
        s += 'e' + RE.re.sub(r'[^.0-9-+]+', '', num_strings[1])
    if s:
        return s
    return None


def normalize_names(names):
    """Coerce a string or nested list of strings into a flat list of strings."""
    if isinstance(names, basestring):
        names = names.split(',')
    names = listify(names)
    return [str(name).strip() for name in names]


def string_stats(strs, valid_chars='012346789', left_pad='0', right_pad='', strip=True):
    """Count the occurrence of a category of valid characters within an iterable of serial numbers, model numbers, or other strings"""
    if left_pad == None:
        left_pad = ''.join(c for c in RE.ASCII_CHARACTERS if c not in valid_chars)
    if right_pad == None:
        right_pad = ''.join(c for c in RE.ASCII_CHARACTERS if c not in valid_chars)

    def normalize(s):
        if strip:
            s = s.strip()
        s = s.lstrip(left_pad)
        s = s.rstrip(right_pad)
        return s

    # should probably check to make sure memory not exceeded
    strs = [normalize(s) for s in strs]
    lengths = collections.Counter(len(s) for s in strs)
    counts = {}
    max_length = max(lengths.keys())

    for i in range(max_length):
        # print i
        for s in strs:
            if i < len(s):
                counts[ i]   = counts.get( i  , 0) + int(s[ i  ] in valid_chars)
                counts[-i-1] = counts.get(-i-1, 0) + int(s[-i-1] in valid_chars)
        long_enough_strings = float(sum(c for l, c in lengths.items() if l >= i))
        counts[i] = counts[i] / long_enough_strings
        counts[-i-1] = counts[-i-1] / long_enough_strings

    return counts


def normalize_serial_number(sn, 
                            max_length=None, left_fill='0', right_fill='', blank='', 
                            valid_chars=' -0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 
                            invalid_chars=None, 
                            strip_whitespace=True, join=False, na=RE.nones):
    r"""Make a string compatible with typical serial number requirements

    # Default configuration strips internal and external whitespaces and retains only the last 10 characters

    >>> normalize_serial_number('1C 234567890             ')
    '0234567890'

    >>> normalize_serial_number('1C 234567890             ', max_length=20)
    '000000001C 234567890'
    >>> normalize_serial_number('Unknown', blank=None, left_fill='')
    ''
    >>> normalize_serial_number('N/A', blank='', left_fill='')
    'A'
    
    >>> normalize_serial_number('1C 234567890             ', max_length=20, left_fill='')
    '1C 234567890'

    Notice how the max_length setting (20) carries over from the previous test!
    >>> len(normalize_serial_number('Unknown', blank=False))
    20
    >>> normalize_serial_number('Unknown', blank=False)
    '00000000000000000000'
    >>> normalize_serial_number(' \t1C\t-\t234567890 \x00\x7f', max_length=14, left_fill='0', valid_chars='0123456789ABC', invalid_chars=None, join=True)
    '0001C234567890'

    Notice how the max_length setting carries over from the previous test!
    >>> len(normalize_serial_number('Unknown', blank=False))
    14

    Restore the default max_length setting
    >>> len(normalize_serial_number('Unknown', blank=False, max_length=10))
    10
    >>> normalize_serial_number('NO SERIAL', blank='--=--', left_fill='')  # doctest: +NORMALIZE_WHITESPACE
    'NO SERIAL'
    >>> normalize_serial_number('NO SERIAL', blank='', left_fill='')  # doctest: +NORMALIZE_WHITESPACE
    'NO SERIAL'

    >>> normalize_serial_number('1C 234567890             ', valid_chars='0123456789')
    '0234567890'
    """
    # All 9 kwargs have persistent default values stored as attributes of the funcion instance
    if max_length is None:
        max_length = normalize_serial_number.max_length
    else:
        normalize_serial_number.max_length = max_length
    if left_fill is None:
        left_fill = normalize_serial_number.left_fill
    else:
        normalize_serial_number.left_fill = left_fill
    if right_fill is None:
        right_fill = normalize_serial_number.right_fill
    else:
        normalize_serial_number.right_fill = right_fill
    if blank is None:
        blank = normalize_serial_number.blank
    else:
        normalize_serial_number.blank = blank
    if valid_chars is None:
        valid_chars = normalize_serial_number.valid_chars
    else:
        normalize_serial_number.valid_chars = valid_chars
    if invalid_chars is None:
        invalid_chars = normalize_serial_number.invalid_chars
    else:
        normalize_serial_number.invalid_chars = invalid_chars
    if strip_whitespace is None:
        strip_whitespace = normalize_serial_number.strip_whitespace
    else:
        normalize_serial_number.strip_whitespace = strip_whitespace
    if join is None:
        join = normalize_serial_number.join
    else:
        normalize_serial_number.join = join
    if na is None:
        na = normalize_serial_number.na
    else:
        normalize_serial_number.na = na

    if invalid_chars is None:
        invalid_chars = (c for c in ascii.all_ if c not in valid_chars)
    invalid_chars = ''.join(invalid_chars)
    sn = str(sn).strip(invalid_chars)
    if strip_whitespace:
        sn = sn.strip()
    if invalid_chars:
        if join:
            sn = sn.translate(None, invalid_chars)
        else:
            sn = multisplit(sn, invalid_chars)[-1]
    sn = sn[-max_length:]
    if strip_whitespace:
        sn = sn.strip()
    if na:
        if isinstance(na, (tuple, set, dict, list)) and sn in na:
            sn = ''
        elif na.match(sn):
            sn = ''
    if not sn and not (blank is False):
        return blank
    if left_fill:
        sn = left_fill * (max_length - len(sn)/len(left_fill)) + sn
    if right_fill:
        sn = sn + right_fill * (max_length - len(sn)/len(right_fill))
    return sn
normalize_serial_number.max_length=10
normalize_serial_number.left_fill='0'
normalize_serial_number.right_fill=''
normalize_serial_number.blank=''
normalize_serial_number.valid_chars=' -0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' 
normalize_serial_number.invalid_chars=None
normalize_serial_number.strip_whitespace=True
normalize_serial_number.join=False
normalize_serial_number.na=RE.nones
invalid_chars=None
strip_whitespace=True
join=False
na=RE.nones


normalize_account_number = normalize_serial_number


def multisplit(s, seps=list(string.punctuation) + list(string.whitespace), blank=True):
    r"""Just like str.split(), except that a variety (list) of seperators is allowed.
    
    >>> multisplit(r'1-2?3,;.4+-', string.punctuation)
    ['1', '2', '3', '', '', '4', '', '']
    >>> multisplit(r'1-2?3,;.4+-', string.punctuation, blank=False)
    ['1', '2', '3', '4']
    >>> multisplit(r'1C 234567890', '\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n' + string.punctuation)
    ['1C 234567890']
    """
    seps = ''.join(seps)
    return [s2 for s2 in s.translate(''.join([(chr(i) if chr(i) not in seps else seps[0]) for i in range(256)])).split(seps[0]) if (blank or s2)]


def make_real(list_of_lists):
    for i, l in enumerate(list_of_lists):
        for j, val in enumerate(l):
            list_of_lists[i][j] = float(normalize_scientific_notation(str(val), ignore_commas=True))
    return list_of_lists


# def linear_correlation(x, y=None, ddof=0):
#     """Pierson linear correlation coefficient (-1 <= plcf <= +1)
#     >>> abs(linear_correlation(range(5), [1.2 * x + 3.4 for x in range(5)]) - 1.0) < 0.000001
#     True
#     # >>> abs(linear_correlation(sci.rand(2, 1000)))  # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
#     # 0.0...
#     """
#     if y is None:
#         if len(x) == 2:
#             y = x[1]
#             x = x[0]
#         elif len(x[0]) ==2:
#             y = [yi for xi, yi in x] 
#             x = [xi for xi, yi in x]
#         else:
#             mat = np.cov(x, ddof=ddof)
#             R = []
#             N = len(mat)
#             for i in range(N):
#                 R += [[1.] * N]
#                 for j in range(i+1,N):
#                     R[i][j] = mat[i,j]
#                     for k in range(N):
#                         R[i][j] /= (mat[k,k] ** 0.5)
#             return R
#     return np.cov(x, y, ddof=ddof)[1,0] / np.std(x, ddof=ddof) / np.std(y, ddof=ddof)


# def best_correlation_offset(x, y, ddof=0):
#     """Find the delay between x and y that maximizes the correlation between them
#     A negative delay means a negative-correlation between x and y was maximized
#     """
#     def offset_correlation(offset, x=x, y=y):
#         N = len(x)
#         if offset < 0:
#             y = [-1 * yi for yi in y]
#             offset = -1 * offset 
#         # TODO use interpolation to allow noninteger offsets
#         return linear_correlation([x[(i - int(offset)) % N] for i in range(N)], y)
#     return sci.minimize(offset_correlation, 0)


def imported_modules():
    for name, val in globals().iteritems():
        if isinstance(val, types.ModuleType):
            yield val


def make_tz_aware(dt, tz='UTC', is_dst=None):
    """Add timezone information to a datetime object, only if it is naive.

    >>> make_tz_aware(datetime.datetime(2001, 9, 8, 7, 6))
    datetime.datetime(2001, 9, 8, 7, 6, tzinfo=<UTC>)
    """
    tz = dt.tzinfo or tz
    try:
        tz = pytz.timezone(tz)
    except AttributeError:
        pass
    return tz.localize(dt, is_dst=is_dst) 


def normalize_datetime(t, time=datetime.timedelta(hours=16)):
    if isinstance(t, datetime.datetime):
        if not t.hours + t.seconds:
            if time:
                t += time
        return t
    if isinstance(t, datetime.date):
        return normalize_datetime(datetime.datetime(t), time=time)
    if isinstance(t, basestring):
        return normalize_datetime(parse_date(t))
    return normalize_datetime(datetime.datetime(*[int(i) for i in t]))


def normalize_date(d):
    if isinstance(d, datetime.date):
        return d
    if isinstance(d, datetime.datetime):
        return datetime.date(d.year, d.month, d.day)
    if isinstance(d, basestring):
        return normalize_date(parse_date(d))
    return normalize_date(datetime.datetime(*[int(i) for i in d]))


def clean_wiki_datetime(dt, squelch=True):
    if isinstance(dt, datetime.datetime):
        return dt
    elif not isinstance(dt, basestring):
        dt = ' '.join(dt)
    try:
        return make_tz_aware(dateutil.parser.parse(dt))
    except:
        if not squelch:
            print("Failed to parse %r as a date" % dt)
    dt = [s.strip() for s in dt.split(' ')]
    # get rid of any " at " or empty strings
    dt = [s for s in dt if s and s.lower() != 'at']

    # deal with the absence of :'s in wikipedia datetime strings

    if RE.month_name.match(dt[0]) or RE.month_name.match(dt[1]):
        if len(dt) >= 5:
            dt = dt[:-2] + [dt[-2].strip(':') + ':' + dt[-1].strip(':')]
            return clean_wiki_datetime(' '.join(dt))
        elif len(dt) == 4 and (len(dt[3]) == 4 or len(dt[0]) == 4):
            dt[:-1] + ['00']
            return clean_wiki_datetime(' '.join(dt))
    elif RE.month_name.match(dt[-2]) or RE.month_name.match(dt[-3]):
        if len(dt) >= 5:
            dt = [dt[0].strip(':') + ':' + dt[1].strip(':')] + dt[2:]
            return clean_wiki_datetime(' '.join(dt))
        elif len(dt) == 4 and (len(dt[-1]) == 4 or len(dt[-3]) == 4):
            dt = [dt[0], '00'] + dt[1:]
            return clean_wiki_datetime(' '.join(dt))

    try:
        return make_tz_aware(dateutil.parser.parse(' '.join(dt)))
    except Exception as e:
        if squelch:
            from traceback import format_exc
            print format_exc(e) +  '\n^^^ Exception caught ^^^\nWARN: Failed to parse datetime string %r\n      from list of strings %r' % (' '.join(dt), dt)
            return dt
        raise(e)


def minmax_len_and_blackwhite_list(s, min_len=1, max_len=256, blacklist=None, whitelist=None, lower=False):
    if min_len > len(s) or len(s) > max_len:
        return False
    if lower:
        s = s.lower()
    if blacklist and s in blacklist:
        return False
    if whitelist and s not in whitelist:
        return False
    return True


def strip_HTML(s):
    """Simple, clumsy, slow HTML tag stripper"""
    result = ''
    total = 0
    for c in s:
        if c == '<':
            total = 1
        elif c == '>':
            total = 0
            result += ' '
        elif total == 0:
            result += c
    return result


def strip_edge_punc(s, punc=None, lower=None, str_type=str):
    if lower is None:
        lower = strip_edge_punc.lower
    if punc is None:
        punc = strip_edge_punc.punc
    if lower:
        s = s.lower()
    if not isinstance(s, basestring):
        return [strip_edge_punc(str_type(s0), punc) for s0 in s]
    return s.strip(punc)
strip_edge_punc.lower = False
strip_edge_punc.punc = PUNC


def get_sentences(s, regex=RE.sentence_sep):
    if isinstance(regex, basestring):
        regex = re.compile(regex)
    return [sent for sent in regex.split(s) if sent]


# this regex assumes "s' " is the end of a possessive word and not the end of an inner quotation, e.g. He said, "She called me 'Hoss'!"
def get_words(s, splitter_regex=RE.word_sep_except_external_appostrophe, 
              preprocessor=strip_HTML, postprocessor=strip_edge_punc, min_len=None, max_len=None, blacklist=None, whitelist=None, lower=False, filter_fun=None, str_type=str):
    r"""Segment words (tokens), returning a list of all tokens 

    Does not return any separating whitespace or punctuation marks.
    Attempts to return external apostrophes at the end of words.
    Comparable to `nltk.word_toeknize`.

    Arguments:
      splitter_regex (str or re): compiled or uncompiled regular expression
        Applied to the input string using `re.split()`
      preprocessor (function): defaults to a function that strips out all HTML tags
      postprocessor (function): a function to apply to each token before return it as an element in the word list
        Applied using the `map()` builtin
      min_len (int): delete all words shorter than this number of characters
      max_len (int): delete all words longer than this number of characters
      blacklist and whitelist (list of str): words to delete or preserve
      lower (bool): whether to convert all words to lowercase
      str_type (type): typically `str` or `unicode`, any type constructor that should can be applied to all words before returning the list

    Returns:
      list of str: list of tokens

    >>> get_words('He said, "She called me \'Hoss\'!". I didn\'t hear.')
    ['He', 'said', 'She', 'called', 'me', 'Hoss', 'I', "didn't", 'hear']
    >>> get_words('The foxes\' oh-so-tiny den was 2empty!')
    ['The', 'foxes', 'oh-so-tiny', 'den', 'was', '2empty']
    """
    # TODO: Get rid of `lower` kwarg (and make sure code that uses it doesn't break) 
    #       That and other simple postprocessors can be done outside of get_words
    postprocessor = postprocessor or str_type
    preprocessor = preprocessor or str_type
    if min_len is None:
        min_len = get_words.min_len
    if max_len is None:
        max_len = get_words.max_len
    blacklist = blacklist or get_words.blacklist
    whitelist = whitelist or get_words.whitelist
    filter_fun = filter_fun or get_words.filter_fun
    lower = lower or get_words.lower
    try:
        s = open(s, 'r')
    except:
        pass
    try:
        s = s.read()
    except:
        pass
    if not isinstance(s, basestring):
        try:
            # flatten the list of lists of words from each obj (file or string)
            return [word for obj in s for word in get_words(obj)]
        except:
            pass
    try:
        s = preprocessor(s)
    except:
        pass
    if isinstance(splitter_regex, basestring):
        splitter_regex = re.compile(splitter_regex)
    s = map(postprocessor, splitter_regex.split(s))
    s = map(str_type, s)
    if not filter_fun:
        return s
    return [word for word in s if filter_fun(word, min_len=min_len, max_len=max_len, blacklist=blacklist, whitelist=whitelist, lower=lower)]
get_words.blacklist = ('', None, '\'', '.', '_', '-')
get_words.whitelist = None
get_words.min_len = 1
get_words.max_len = 256
get_words.lower = False
get_words.filter_fun = minmax_len_and_blackwhite_list


def pluralize_field_name(names=None, retain_prefix=False):
    if not names:
        return ''
    elif isinstance(names, basestring):
        if retain_prefix:
            split_name = names
        else:
            split_name = names.split('__')[-1]
        if not split_name:
            return names
        elif 0 < len(split_name) < 4 or split_name.lower()[-4:] not in ('call', 'sale', 'turn'):
            return split_name
        else:
            return split_name + 's'
    else:
        return [pluralize_field_name(name) for name in names]
pluralize_field_names = pluralize_field_name


def tabulate(lol, headers, eol='\n'):
    """Use the pypi tabulate package instead!"""
    yield '| %s |' % ' | '.join(headers) + eol
    yield '| %s:|' % ':| '.join(['-'*len(w) for w in headers]) + eol
    for row in lol:
        yield '| %s |' % '  |  '.join(str(c) for c in row) + eol


def intify(obj, str_fun=str, use_ord=True, use_hash=True, use_len=True):
    """FIXME: this is unpythonic and does things you don't expect!

    FIXME: rename to "integer_from_category"

    Returns an integer representative of a categorical object (string, dict, etc)

    >>> intify('1.2345e10')
    12345000000
    >>> intify([12]), intify('[99]'), intify('(12,)')
    (91, 91, 40)
    >>> intify('A'), intify('a'), intify('AAA'), intify('B'), intify('BB')
    (97, 97, 97, 98, 98)
    >>> intify(272)
    272
    >>> intify(float('nan'), use_ord=False, use_hash=False, str_fun=None)
    >>> intify(float('nan'), use_ord=False, use_hash=False, use_len=False)
    >>> intify(float('nan')), intify('n'), intify(None)
    (110, 110, 110)
    >>> intify(None, use_ord=False, use_hash=False, use_len=False)
    >>> intify(None, use_ord=False, use_hash=False, str_fun=False)
    >>> intify(None, use_hash=False, str_fun=False) 
    """
    try:
        return int(obj)
    except:
        pass
    try:
        float_obj = float(obj)
        if float('-inf') < float_obj < float('inf'):
            # WARN: This will increment sys.maxint by +1 and decrement sys.maxint by -1!!!!
            #       But hopefully these cases will be dealt with as expected, above
            return int(float_obj)
    except:
        pass
    if not str_fun:
        str_fun = lambda x:x
    if use_ord:    
        try:
            return ord(str_fun(obj)[0].lower())
        except:
            pass
    if use_hash:  
        try:
            return hash(str_fun(obj))
        except:
            pass
    if use_len:
        try:
            return len(obj)
        except:
            pass
        try:
            return len(str_fun(obj))
        except:
            pass
    return None



def listify(values, N=1, delim=None):
    """Return an N-length list, with elements values, extrapolating as necessary.

    >>> listify("don't split into characters")
    ["don't split into characters"]
    >>> listify("len = 3", 3)
    ['len = 3', 'len = 3', 'len = 3']
    >>> listify("But split on a delimeter, if requested.", delim=',')
    ['But split on a delimeter', ' if requested.']
    >>> listify(["obj 1", "obj 2", "len = 4"], N=4)
    ['obj 1', 'obj 2', 'len = 4', 'len = 4']
    >>> listify(iter("len=7"), N=7)
    ['l', 'e', 'n', '=', '7', '7', '7']
    >>> listify(iter("len=5"))
    ['l', 'e', 'n', '=', '5']
    >>> listify(None, 3)
    [[], [], []]
    >>> listify([None],3)
    [None, None, None]
    >>> listify([], 3)
    [[], [], []]
    >>> listify('', 2)
    ['', '']
    >>> listify(0)
    [0]
    >>> listify(False, 2)
    [False, False]
    """
    ans = [] if values is None else values

    # convert non-string non-list iterables into a list
    if hasattr(ans, '__iter__') and not isinstance(ans, basestring):
        ans = list(ans)
    else:
        # split the string (if possible)
        if isinstance(delim, basestring) and isinstance(ans, basestring):
            try:
                ans = ans.split(delim)
            except:
                ans = [ans]
        else:
            ans = [ans]

    # pad the end of the list if a length has been specified
    if len(ans):
        if len(ans) < N and N > 1:
            ans += [ans[-1]] * (N - len(ans))
    else:
        if N > 1:
            ans = [[]] * N

    return ans


def tuplify(values, N=1, delim=None):
    return tuple(listify(values, N=N, delim=delim))


def unlistify(l, depth=1, typ=list, get=None):
    """Return the desired element in a list ignoring the rest.

    >>> unlistify([1,2,3])
    1
    >>> unlistify([1,[4, 5, 6],3], get=1)
    [4, 5, 6]
    >>> unlistify([1,[4, 5, 6],3], depth=2, get=1)
    5
    >>> unlistify([1,(4, 5, 6),3], depth=2, get=1)
    (4, 5, 6)
    >>> unlistify([1,2,(4, 5, 6)], depth=2, get=2)
    (4, 5, 6)
    >>> unlistify([1,2,(4, 5, 6)], depth=2, typ=(list, tuple), get=2)
    6
    """
    i = 0
    if depth is None:
        depth = 1
    index_desired = get or 0
    while i < depth and isinstance(l, typ):
        if len(l):
            if len(l) > index_desired:
                l = l[index_desired]
                i += 1
        else:
            return l
    return l


def is_ignorable_str(s, ignorable_strings=(), lower=True, filename=True, startswith=True):
    ignorable_strings = listify(ignorable_strings)
    if not (lower or filename or startswith):
        return s in ignorable_strings
    for ignorable in ignorable_strings:
        if lower:
            ignorable = ignorable.lower()
            s = s.lower()
        if filename:
            s = s.split(os.path.sep)[-1]
        if startswith and s.startswith(ignorable):
            return True
        elif s == ignorable:
            return True


def strip_keys(d, nones=False, depth=0):
    r"""Strip whitespace from all dictionary keys, to the depth indicated

    >>> strip_keys({' a': ' a', ' b\t c ': {'d e  ': 'd e  '}}) == {'a': ' a', 'b\t c': {'d e  ': 'd e  '}}
    True
    >>> strip_keys({' a': ' a', ' b\t c ': {'d e  ': 'd e  '}}, depth=100) == {'a': ' a', 'b\t c': {'d e': 'd e  '}}
    True
    """
    ans = type(d)((str(k).strip(), v) for (k, v) in OrderedDict(d).iteritems() if (not nones or (str(k).strip() and str(k).strip() != 'None')))
    if int(depth) < 1:
        return ans
    if int(depth) > strip_keys.MAX_DEPTH:
        warnings.warn(RuntimeWarning("Maximum recursion depth allowance (%r) exceeded." % strip_keys.MAX_DEPTH))
    for k, v in ans.iteritems():
        if isinstance(v, collections.Mapping):
            ans[k] = strip_keys(v, nones=nones, depth=int(depth)-1)
    return ans
strip_keys.MAX_DEPTH = 1e6


def str_from_table(table, sep='\t', eol='\n', max_rows=100000000, max_cols=1000000):
    max_rows = min(max_rows, len(table))
    return eol.join([sep.join(list(str(field) for field in row[:max_cols])) for row in table[:max_rows]])


def get_table_from_csv(filename='ssg_report_aarons_returns.csv', delimiter=',', dos=False):
    """Dictionary of sequences from CSV file"""
    table = []
    with open(filename, 'rb') as f:
        reader = csv.reader(f, dialect='excel', delimiter=delimiter)
        for row in reader:
            table += [row]
    if not dos:
        return table
    return dos_from_table(table)


def save_sheet(table, filename, ext='tsv', verbosity=0):
    if ext.lower() == 'tsv':
        sep = '\t'
    else:
        sep = ','
    s = str_from_table(table, sep=sep)
    if verbosity > 2:
        print s
    if verbosity:
        print 'Saving ' + filename + '.' + ext
    with open(filename + '.' + ext, 'w') as fpout:
        fpout.write(s)


def save_sheets(tables, filename, ext='.tsv', verbosity=0):
    for i, table in enumerate(tables):
        save_sheet(table, filename + '_Sheet%d' % i, ext=ext, verbosity=verbosity)


def shorten(s, max_len=16):
    """Attempt to shorten a phrase by deleting words at the end of the phrase

    >>> shorten('Hello World!')
    'Hello World'
    >>> shorten("Hello World! I'll talk your ear off!", 15)
    'Hello World'
    """
    short = s
    words = [abbreviate(word) for word in get_words(s)]
    for i in xrange(len(words), 0, -1):
        short = ' '.join(words[:i])
        if len(short) <= max_len:
            break
    return short[:max_len]


def abbreviate(s):
    """Some basic abbreviations

    TODO: load a large dictionary of abbreviations from NLTK, etc
    """
    return abbreviate.words.get(s, s)
abbreviate.words = {'account': 'acct', 'number': 'num', 'customer': 'cust', 'member': 'membr', 'building': 'bldg', 'serial number': 'SN', 'social security number': 'SSN'}


def remove_internal_vowels(s, space=''):
    # because this pattern overlaps for vowels separated by a single or no consonant, it must be run several times
    internal_vowel = re.compile(r'([A-Za-z])[aeiou]([A-Za-z])')
    strlen = len(s)
    while True:
        s = internal_vowel.sub(r'\1\2', s)
        if len(s) < strlen:
            strlen = len(s)
        else:
            break
    return re.sub(r'\s', space, s)


def normalize_year(y):
    y = RE.not_digit_list.sub('', str(y))
    try:
        y = int(y)
    except:
        y = None
    if 0 <= y < 70:
        y += 2000
    elif 70 <= y < 100:
        y += 1900
    return y


def generate_kmers(seq, k=4):
    """Return a generator of all the unique substrings (k-mer or q-gram strings) within a sequence/string

    Not effiicent for large k and long strings.
    Doesn't form substrings that are shorter than k, only exactly k-mers

    Used for algorithms like UniqTag for genome unique identifier locality sensitive hashing.

    jellyfish is a C implementation of k-mer counting

    If seq is a string generate a sequence of k-mer string
    If seq is a sequence of strings then generate a sequence of generators or sequences of k-mer strings
    If seq is a sequence of sequences of strings generate a sequence of sequence of generators ...

    Default k = 4 because that's the length of a gene base-pair?

    >>> ' '.join(generate_kmers('AGATAGATAGACACAGAAATGGGACCACAC'))
    'AGAT GATA ATAG TAGA AGAT GATA ATAG TAGA AGAC GACA ACAC CACA ACAG CAGA AGAA GAAA AAAT AATG ATGG TGGG GGGA GGAC GACC ACCA CCAC CACA ACAC'
    """
    if isinstance(seq, basestring):
        for i in range(len(seq) - k + 1):
           yield seq[i:i+k]
    elif isinstance(seq, (int, float, decimal.Decimal)):
        for s in generate_kmers(str(seq)):
            yield s
    else:
        for s in seq:
            yield generate_kmers(s, k)


def datetime_histogram(seq):
    """Plot a histogram of datetimes from a sequence (list, tuple, iterator) of date or datetimes"""
    raise NotImplementedError()


def kmer_tuple(seq, k=4):
    """Return a tuple all the unique substrings (k-mer or q-gram strings) within a sequence/string

    Not effiicent for large k and long strings.
    Doesn't form substrings that are shorter than k, only exactly k-mers

    Used for algorithms like UniqTag for genome unique identifier locality sensitive hashing.

    jellyfish is a C implementation of k-mer counting

    If seq is a string generate a sequence of k-mer string
    If seq is a sequence of strings then generate a sequence of generators or sequences of k-mer strings
    If seq is a sequence of sequences of strings generate a sequence of sequence of generators ...

    Default k = 4 because that's the length of a gene base-pair?

    Examples:
        # >>> kmer_tuple(['AGATAGATAG', 'ACACAGAAAT', 'GGGACCACAC'], k=4)
        # (('AGAT', 'GATA', 'ATAG', 'TAGA', 'AGAT', 'GATA', 'ATAG'),
        #  ('ACAC', 'CACA', 'ACAG', 'CAGA', 'AGAA', 'GAAA', 'AAAT'),
        #  ('GGGA', 'GGAC', 'GACC', 'ACCA', 'CCAC', 'CACA', 'ACAC'))
        >>> ' '.join(kmer_tuple('AGATAGATAGACACAGAAATGGGACCACAC'))
        'AAAT AATG ACAC ACAC ACAG ACCA AGAA AGAC AGAT AGAT ATAG ATAG ATGG CACA CACA CAGA CCAC GAAA GACA GACC GATA GATA GGAC GGGA TAGA TAGA TGGG'
    """
    return tuple(sorted(generate_kmers(seq, k=k)))


def kmer_counter(seq, k=4):
    """Return a sequence of all the unique substrings (k-mer or q-gram) within a short (<128 symbol) string

    Used for algorithms like UniqTag for genome unique identifier locality sensitive hashing.

    jellyfish is a C implementation of k-mer counting

    If seq is a string generate a sequence of k-mer string
    If seq is a sequence of strings then generate a sequence of generators or sequences of k-mer strings
    If seq is a sequence of sequences of strings generate a sequence of sequence of generators ...

    Default k = 4 because that's the length of a gene base-pair?

    >>> kmer_counter('AGATAGATAGACACAGAAATGGGACCACAC') == collections.Counter({'ACAC': 2, 'ATAG': 2, 'CACA': 2, 'TAGA': 2, 'AGAT': 2, 'GATA': 2, 'AGAC': 1, 'ACAG': 1, 'AGAA': 1, 'AAAT': 1, 'TGGG': 1, 'ATGG': 1, 'ACCA': 1, 'GGAC': 1, 'CCAC': 1, 'CAGA': 1, 'GAAA': 1, 'GGGA': 1, 'GACA': 1, 'GACC': 1, 'AATG': 1})
    True
    """
    if isinstance(seq, basestring):
        return collections.Counter(generate_kmers(seq, k))


def kmer_set(seq, k=4):
    """Return the set of unique k-length substrings within a the sequence/string `seq`

    Implements formula:
    C_k(s) = C(s) ∩ Σ^k 
    from http://biorxiv.org/content/early/2014/08/01/007583

    >>> sorted(kmer_set('AGATAGATAGACACAGAAATGGGACCACAC'))
    ['AAAT', 'AATG', 'ACAC', 'ACAG', 'ACCA', 'AGAA', 'AGAC', 'AGAT', 'ATAG', 'ATGG', 'CACA', 'CAGA', 'CCAC', 'GAAA', 'GACA', 'GACC', 'GATA', 'GGAC', 'GGGA', 'TAGA', 'TGGG']
    """
    if isinstance(seq, basestring):
        return set(generate_kmers(seq, k))


# def kmer_frequency(seq_of_seq, km=None):
#     """Count the number of sequences in seq_of_seq that contain a given kmer `km`

#     From http://biorxiv.org/content/early/2014/08/01/007583, implements the formula:
#     f(t, S) = |{s | t ∈ C^k(s) ∧ s ∈ S}|
#     where:
#     t = km
#     S = seq_of_seq
#     >>> kmer_frequency(['AGATAGATAG', 'ACACAGAAAT', 'GGGACCACAC'], km=4)
    
#     """
#     if km and isinstance(km, basestring):
#         return sum(km in counter for counter in kmer_counter(seq_of_seq, len(km)))
#     km = int(km)
#     counter = collections.Counter()
#     counter += collections.Counter(tuple(sorted(set(kmer_counter(seq, km)))) for seq in seq_of_seq)
#     return counter


# def uniq_tag(seq, k=4, other_strings=None):
#     """Hash that is the same for similar strings and can serve as an abbreviation for a string

#     Based on UniqTag:
#     http://biorxiv.org/content/early/2014/08/01/007583
#     Which was inspired by MinHasH:
#     http://en.wikipedia.org/wiki/MinHash

#     t_u = min arg min t ∈ C k(s) f(t, S)
#     uk(s, S) = min (arg_min((t ∈ C^k(s)), f(t, S))

#     uk(s, S) = "the UniqTag, the lexicographically minimal k-mer of those k-mers of s that are least frequent in S."

#     the "k-mers of s" can be found with kmer_set()
#     the frequencies of those k-mers in other_stirngs, S, should be provided by kmer_frequency(other_strings, km) for km in kmer_set(s)

#     >>> uniq_tag('Hello World')

#     """
#     # FIXME: UNTESTED!
#     if not other_strings:
#         if isinstance(seq, basestring):
#             other_strings = (seq,)
#         else:
#             other_strings = tuple(seq)
#         return uniq_tag(other_strings[0], other_strings)
#     other_strings = set(other_strings)
#     if isinstance(seq, basestring):
#         kms = kmer_set(seq)
#         km_frequencies = ((sum(km in kmer_set(s, k), s) for s in other_strings) for km in kms)
#         print min(km_frequencies)
#         return min(km_frequencies)[1]
#     return tuple(uniq_tag(s, other_strings) for s in seq)


def count_duplicates(items):
    """Return a dict of objects and thier counts (like a Counter), but only count > 1"""
    c = collections.Counter(items)
    return dict((k, v) for (k,v) in c.iteritems() if v > 1)



# def markdown_stats(doc):
#     """Compute statistics about the string or document provided.

#     Returns:
#         dict: e.g. {'pages': 24, 'words': 1234, 'vocabulary': 123, 'reaading level': 3, ...}
#     """
#     sentence_detector = nltk.data.load('tokenizers/punkt/english.pickle')
#     sentences = sentence_detector.tokenize(doc)
#     tokens = nltk.tokenize.punkt.PunktWordTokenizer().tokenize(doc)
#     vocabulary = collections.Counter(tokens)
    
#     return collections.OrderedDict([
#         ('lines', sum([bool(l.strip().strip('-').strip()) for l in doc.split('\n')])),
#         ('pages', sum([bool(l.strip().startswith('---')) for l in doc.split('\n')]) + 1),
#         ('tokens', len(tokens)),
#         ('sentences', len(sentences)),
#         ('vocabulary', len(vocabulary.keys())),
#         ])


def slug_from_dict(d, max_len=128, delim='-'):
    """Produce a slug (short URI-friendly string) from an iterable Mapping (dict, OrderedDict)

    >>> slug_from_dict({'a': 1, 'b': 'beta', ' ': 'alpha'})
    '1-alpha-beta'
    """
    return slug_from_iter(d.values(), max_len=max_len, delim=delim)


def slug_from_iter(it, max_len=128, delim='-'):
    """Produce a slug (short URI-friendly string) from an iterable (list, tuple, dict)

    >>> slug_from_iter(['.a.', '=b=', '--alpha--'])
    'a-b-alpha'
    """

    nonnull_values = [str(v) for v in it if v or ((isinstance(v, (long, int, float, Decimal)) and str(v)))]
    return slugify(delim.join(shorten(v, max_len=int(float(max_len) / len(nonnull_values))) for v in nonnull_values), word_boundary=True)


def tfidf(corpus):
    """Compute a TFIDF matrix (Term Frequency and Inverse Document Freuqency matrix)"""
    raise NotImplementedError("Google TFIDF for canonical implementations")


def shakeness(doc):
    """Determine how similar a document's vocabulary is to Shakespeare's"""
    raise NotImplementedError("Import a Shakespear corpus and compare the distribution of words there to the ones in the sample doc (vocabulary similarity)")


def slash_product(string_or_seq, slash='/', space=' '):
    """Return a list of all possible meanings of a phrase containing slashes

    TODO:
        - Code is not in standard Sedgewick recursion form
        - Simplify by removing one of the recursive calls?
        - Simplify by using a list comprehension?

    >>> slash_product("The challenging/confusing interview didn't end with success/offer")  # doctest: +NORMALIZE_WHITESPACE
    ["The challenging interview didn't end with success",
     "The challenging interview didn't end with offer",
     "The confusing interview didn't end with success",
     "The confusing interview didn't end with offer"]
    >>> slash_product('I say goodbye/hello cruel/fun world.')  # doctest: +NORMALIZE_WHITESPACE
    ['I say goodbye cruel world.',
     'I say goodbye fun world.',
     'I say hello cruel world.',
     'I say hello fun world.']
    >>> slash_product('I say goodbye/hello/bonjour cruelness/fun/world')  # doctest: +NORMALIZE_WHITESPACE
    ['I say goodbye cruelness',
     'I say goodbye fun',
     'I say goodbye world',
     'I say hello cruelness',
     'I say hello fun',
     'I say hello world',
     'I say bonjour cruelness',
     'I say bonjour fun',
     'I say bonjour world']
    """
    # Terminating case is a sequence of strings without any slashes
    if not isinstance(string_or_seq, basestring):
        # If it's not a string and has no slashes, we're done
        if not any(slash in s for s in string_or_seq):
            return list(string_or_seq)
        ans = []
        for s in string_or_seq:
            # slash_product of a string will always return a flat list
            ans += slash_product(s)
        return slash_product(ans)
    # Another terminating case is a single string without any slashes
    if not slash in string_or_seq:
        return [string_or_seq]
    # The third case is a string with some slashes in it
    i = string_or_seq.index(slash)
    head, tail = string_or_seq[:i].split(space), string_or_seq[i+1:].split(space)
    alternatives = head[-1], tail[0]
    head, tail = space.join(head[:-1]), space.join(tail[1:])
    return slash_product([space.join([head, word, tail]).strip(space) for word in alternatives])


def is_valid_american_date_string(s, require_year=True):
    if not isinstance(s, basestring):
        return False
    if require_year and len(s.split('/')) != 3:
        return False
    return bool(1 <= int(s.split('/')[0]) <= 12 and 1 <= int(s.split('/')[1]) <= 31)


def make_date(dt, date_parser=parse_date):
    """Coerce a datetime or string into datetime.date object

    Arguments:
      dt (str or datetime.datetime or atetime.time or numpy.Timestamp): time or date 
        to be coerced into a `datetime.date` object

    Returns:
      datetime.time: Time of day portion of a `datetime` string or object

    >>> make_date('')
    datetime.date(1970, 1, 1)
    >>> make_date(None)
    datetime.date(1970, 1, 1)
    >>> make_date("11:59 PM") == datetime.date.today()
    True
    >>> make_date(datetime.datetime(1999, 12, 31, 23, 59, 59))
    datetime.date(1999, 12, 31)
    """
    if not dt:
        return datetime.date(1970, 1, 1)
    if isinstance(dt, basestring):
        dt = date_parser(dt)
    try:
        dt = dt.timetuple()[:3]
    except:
        dt = tuple(dt)[:3]
    return datetime.date(*dt)


def make_datetime(dt, date_parser=parse_date):
    """Coerce a datetime or string into datetime.datetime object

    Arguments:
      dt (str or datetime.datetime or atetime.time or numpy.Timestamp): time or date 
        to be coerced into a `datetime.date` object

    Returns:
      datetime.time: Time of day portion of a `datetime` string or object

    >>> make_date('')
    datetime.date(1970, 1, 1)
    >>> make_date(None)
    datetime.date(1970, 1, 1)
    >>> make_date("11:59 PM") == datetime.date.today()
    True
    >>> make_date(datetime.datetime(1999, 12, 31, 23, 59, 59))
    datetime.date(1999, 12, 31)
    """
    if isinstance(dt, (datetime.datetime, pd.Timestamp, pd.np.datetime64)):
        return dt
    if isinstance(dt, float):
        return datetime_from_ordinal_float(dt)
    if isinstance(dt, datetime.date):
        return datetime.datetime(dt.year, dt.month, dt.day)
    if isinstance(dt, datetime.time):
        return datetime.datetime(1, 1, 1, dt.hour, dt.minute, dt.second, dt.microsecond)
    if not dt:
        return datetime.datetime(1970, 1, 1)
    if isinstance(dt, basestring):
        return date_parser(dt)
    try:
        return datetime.datetime(*dt.timetuple()[:7])
    except:
        dt = list(dt)
        if 1 <= len(dt) <= 9:
            try:
                return datetime.datetime(*dt[:7])
            except:
                pass
    return [make_datetime(val) for val in dt]


def make_time(dt, date_parser=parse_date):
    """Ignore date information in a datetime string or object

    Arguments:
      dt (str or datetime.datetime or atetime.time or numpy.Timestamp): time or date 
        to be coerced into a `datetime.time` object

    Returns:
      datetime.time: Time of day portion of a `datetime` string or object

    >>> make_time(None)
    datetime.time(0, 0)
    >>> make_time("")
    datetime.time(0, 0)
    >>> make_time("11:59 PM")
    datetime.time(23, 59)
    >>> make_time(datetime.datetime(1999, 12, 31, 23, 59, 59))
    datetime.time(23, 59, 59)
    """
    if not dt:
        return datetime.time(0, 0)
    if isinstance(dt, basestring):
        try:
            dt = date_parser(dt)
        except:
            print_exc()
            print 'Unable to parse datetime string: {0}'.format(dt)
    try:
        dt = dt.timetuple()[3:6]
    except:
        dt = tuple(dt)[3:6]
    return datetime.time(*dt)


def quantize_datetime(dt, resolution=None):
    """Quantize a datetime to integer years, months, days, hours, minutes, seconds or microseconds
    
    Also works with a `datetime.timetuple` or `time.struct_time` or a 1to9-tuple of ints or floats.
    Also works with a sequenece of struct_times, tuples, or datetimes

    >>> quantize_datetime(datetime.datetime(1970,1,2,3,4,5,6), resolution=3)
    datetime.datetime(1970, 1, 2, 0, 0)

    Notice that 6 is the highest resolution value with any utility
    >>> quantize_datetime(datetime.datetime(1970,1,2,3,4,5,6), resolution=7)
    datetime.datetime(1970, 1, 2, 3, 4, 5)
    >>> quantize_datetime(datetime.datetime(1971,2,3,4,5,6,7), 1)
    datetime.datetime(1971, 1, 1, 0, 0)
    """
    # FIXME: this automatically truncates off microseconds just because timtuple() only goes out to sec
    resolution = int(resolution or 6)
    if hasattr(dt, 'timetuple'):
        dt = dt.timetuple()  # strips timezone info

    if isinstance(dt, time.struct_time):
        # strip last 3 fields (tm_wday, tm_yday, tm_isdst)
        dt = list(dt)[:6]
        # struct_time has no microsecond, but accepts float seconds
        dt += [int((dt[5] - int(dt[5])) * 1000000)]
        dt[5] = int(dt[5])
        return datetime.datetime(*(dt[:resolution] + [1] * max(3 - resolution , 0)))

    if isinstance(dt, tuple) and len(dt) <= 9 and all(isinstance(val, (float, int)) for val in dt):
        dt = list(dt) + [0] * (max(6 - len(dt), 0))
        # if the 6th element of the tuple looks like a float set of seconds need to add microseconds
        if len(dt) == 6 and isinstance(dt[5], float):
                dt = list(dt) + [1000000 * (dt[5] - int(dt[5]))]
                dt[5] = int(dt[5])
        dt = tuple(int(val) for val in dt)
        return datetime.datetime(*(dt[:resolution] + [1] * max(resolution - 3, 0)))

    return [quantize_datetime(value) for value in dt]


def ordinal_float(dt):
    """Like datetime.ordinal, but rather than integer allows fractional days (so float not ordinal at all)

    Similar to the Microsoft Excel numerical representation of a datetime object

    >>> ordinal_float(datetime.datetime(1970, 1, 1))
    719163.0
    >>> ordinal_float(datetime.datetime(1, 2, 3, 4, 5, 6, 7))  # doctest: +ELLIPSIS
    34.1702083334143...
    """
    try:
        return dt.toordinal() + ((((dt.microsecond / 1000000.) + dt.second) / 60. + dt.minute) / 60 + dt.hour) / 24.
    except:
        try:
            return ordinal_float(make_datetime(dt))
        except:
            pass
    dt = list(make_datetime(val) for val in dt)
    assert(all(isinstance(val, datetime.datetime) for val in dt))
    return [ordinal_float(val) for val in dt]


def datetime_from_ordinal_float(days):
    """Inverse of `ordinal_float()`, converts a float number of days back to a `datetime` object

    >>> dt = datetime.datetime(1970, 1, 1) 
    >>> datetime_from_ordinal_float(ordinal_float(dt)) == dt
    True
    >>> dt = datetime.datetime(1, 2, 3, 4, 5, 6, 7) 
    >>> datetime_from_ordinal_float(ordinal_float(dt)) == dt
    True
    """
    if isinstance(days, (float, int)):
        dt = datetime.datetime.fromordinal(int(days))
        seconds = (days - int(days)) * 3600. * 24.
        microseconds = (seconds - int(seconds)) * 1000000
        return dt + datetime.timedelta(days=0, seconds=int(seconds), microseconds=int(round(microseconds)))
    return [datetime_from_ordinal_float(d) for d in days]


def timetag_str(dt=None, sep='-', filler='0', resolution=6):
    """Generate a date-time tag suitable for appending to a file name.

    >>> timetag_str(resolution=3) == '-'.join('{0:02d}'.format(i) for i in tuple(datetime.datetime.now().timetuple()[:3]))
    True
    >>> timetag_str(datetime.datetime(2004,12,8,1,2,3,400000))
    '2004-12-08-01-02-03'
    >>> timetag_str(datetime.datetime(2004,12,8))
    '2004-12-08-00-00-00'
    >>> timetag_str(datetime.datetime(2003,6,19), filler='')
    '2003-6-19-0-0-0'
    """
    resolution = int(resolution or 6)
    if sep in (None, False):
        sep = ''
    sep = str(sep)
    dt = datetime.datetime.now() if dt is None else dt
    # FIXME: don't use timetuple which truncates microseconds
    return sep.join(('{0:' + filler + ('2' if filler else '') + 'd}').format(i) for i in tuple(dt.timetuple()[:resolution]))
timestamp_str = make_timestamp = make_timetag = timetag_str


def days_since(dt, dt0=datetime.datetime(1970, 1, 1, 0, 0, 0)):
    return ordinal_float(dt) - ordinal_float(dt0)
