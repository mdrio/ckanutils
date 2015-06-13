#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: sw=4:ts=4:expandtab

""" Miscellaneous CKAN Datastore scripts """

from __future__ import (
    absolute_import, division, print_function, with_statement,
    unicode_literals)

import argparse
import traceback
import sys

from os import environ, path as p
from manager import Manager
from . import utils
from ckanutils.ckan import CKAN, CKAN_KEYS


manager = Manager()
manager.arg('version', 'v')

USER_AGENT = 'ckanapiexample/1.0'
API_ENV = 'CKAN_API_KEY'
HASH_TABLE_ENV = 'CKAN_HASH_TABLE_ID'
PROD_REMOTE_ENV = 'CKAN_PROD_REMOTE_URL'
DEV_REMOTE_ENV = 'CKAN_DEV_REMOTE_URL'

CHUNKSIZE_ROWS = 10**3
CHUNKSIZE_BYTES = 2**20

CKAN_REMOTE = 'http://test-data.hdx.rwlabs.org'
HASH_TABLE_ID = '4bc825fb-2c7e-49db-9133-ba4a9fa26868'
# USER_AGENT = 'HDX-Simon'


def update_resource(ckan, resource_id, filepath, **kwargs):
    chunk_rows = kwargs.get('chunksize_rows')
    primary_key = kwargs.get('primary_key')
    method = 'upsert' if primary_key else 'insert'
    create_keys = ['aliases', 'primary_key', 'indexes']

    records = iter(utils.read_csv(filepath, **kwargs))
    fields = utils.gen_fields(records.next().keys())
    create_kwargs = dict((k, v) for k, v in kwargs.items() if k in create_keys)

    if not primary_key:
        ckan.delete_table(resource_id)

    insert_kwargs = {'chunksize': chunk_rows, 'method': method}
    ckan.create_table(resource_id, fields, **create_kwargs)
    ckan.insert_records(resource_id, records, **insert_kwargs)


def update_hash_table(ckan, resource_id, resource_hash):
    create_kwargs = {
        'resource_id': ckan.hash_table_id,
        'fields': [
            {'id': 'datastore_id', 'type': 'text'},
            {'id': 'hash', 'type': 'text'}],
        'primary_key': 'datastore_id'
    }

    ckan.create_table(**create_kwargs)
    records = [{'datastore_id': resource_id, 'hash': resource_hash}]
    ckan.insert_records(ckan.hash_table_id, records, method='upsert')

@manager.command
def ver():
    """Show ckanny version"""
    from . import __version__ as version
    print('v%s' % version)

@manager.arg('resource_id', help='the resource id')
@manager.arg('remote', 'r', help='the remote ckan url')
@manager.arg('api_key', 'k', help='the api key (uses %s ENV if available)' % API_ENV,
    default=environ.get(API_ENV))
@manager.arg(
    'hash_table_id', 'H', help='the hash table resource id (uses %s ENV if available)' % HASH_TABLE_ENV,
    default=environ.get(HASH_TABLE_ENV))
@manager.arg('user_agent', 'u', help='the user agent',
    default=USER_AGENT)
@manager.arg('chunksize_rows', 'c', help='number of rows to write at a time',
    default=CHUNKSIZE_ROWS)
@manager.arg('chunksize_bytes', 'C', help='number of bytes to read/write at a time',
    default=CHUNKSIZE_BYTES)
@manager.arg(
    'primary_key', 'p', help="Unique field(s), e.g., 'field1,field2'.")
@manager.arg(
    'quiet', 'q', help='suppress debug statements', type=bool, default=False)
@manager.arg(
    'force', 'F', help="update resource even if it hasn't changed.",
    type=bool, default=False)
@manager.command
def dsupdate(resource_id, **kwargs):
    """Update a datastore table"""
    chunk_bytes = kwargs.get('chunksize_bytes')
    force = kwargs.get('force')
    ckan_kwargs = dict((k, v) for k, v in kwargs.items() if k in CKAN_KEYS)

    try:
        ckan = CKAN(**kwargs)
        r, filepath = ckan.fetch_resource(resource_id, chunksize=chunk_bytes)

        if ckan.hash_table_id:
            old_hash = ckan.get_hash(resource_id)
            new_hash = utils.hash_file(filepath, chunksize=chunk_bytes)
            doesnt_need_update = new_hash == old_hash

        if ckan.hash_table_id and doesnt_need_update and not force:
            print('No new data found. Not updating datastore.')
            sys.exit(0)
        elif ckan.hash_table_id and force:
            print('No new data found, but update forced. Updating datastore...')
        elif ckan.hash_table_id:
            print('New data found. Updating datastore...')
        else:
            print('`hash_table_id` not set. Updating datastore...')

        kwargs['encoding'] = r.encoding
        update_resource(ckan, resource_id, filepath, **kwargs)

        if ckan.hash_table_id:
            update_hash_table(ckan, resource_id, new_hash)
    except Exception as err:
        sys.stderr.write('ERROR: %s\n' % str(err))
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
    finally:
        print('Removing tempfile...')
        os.unlink(filename)


@manager.arg('resource_id', help='the resource id')
@manager.arg('remote', 'r', help='the remote ckan url')
@manager.arg('api_key', 'k', help='the api key (uses %s ENV if available)' % API_ENV,
    default=environ.get(API_ENV))
@manager.arg('user_agent', 'u', help='the user agent',
    default=USER_AGENT)
@manager.arg(
    'filters', 'f', help='the filters to apply before deleting, e.g., {"name": "fred"}')
@manager.command
def dsdelete(resource_id, **kwargs):
    """Delete a datastore table"""
    ckan_kwargs = dict((k, v) for k, v in kwargs.items() if k in CKAN_KEYS)

    try:
        ckan = CKAN(**ckan_kwargs)
        ckan.delete_table(resource_id, filters=kwargs.get('filters'))
    except Exception as err:
        sys.stderr.write('ERROR: %s\n' % str(err))
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)


if __name__ == '__main__':
    manager.main()
