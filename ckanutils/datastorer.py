#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: sw=4:ts=4:expandtab

""" Miscellaneous CKAN Datastore scripts """

from __future__ import (
    absolute_import, division, print_function, with_statement,
    unicode_literals)

import traceback
import sys

from StringIO import StringIO
from os import unlink, environ, path as p
from tempfile import NamedTemporaryFile
from manager import Manager
from xattr import xattr
from tabutils import process as tup, io as tio

from . import api

manager = Manager()


def get_message(changed, force):
    if not (changed or force):
        message = 'No new data found. Not updating datastore.'
    elif not changed and force:
        message = 'No new data found, but update forced.'
        message += ' Updating datastore...'
    elif changed:
        message = 'New data found. Updating datastore...'

    return message


@manager.arg(
    'resource_id', help='the resource id', nargs='?', default=sys.stdin)
@manager.arg(
    'remote', 'r', help='the remote ckan url (uses `%s` ENV if available)' %
    api.REMOTE_ENV, default=environ.get(api.REMOTE_ENV))
@manager.arg(
    'api_key', 'k', help='the api key (uses `%s` ENV if available)' %
    api.API_KEY_ENV, default=environ.get(api.API_KEY_ENV))
@manager.arg(
    'hash_table', 'H', help='the hash table package id',
    default=api.DEF_HASH_PACK)
@manager.arg(
    'hash_group', 'g', help="the hash table's owning organization",
    default='HDX')
@manager.arg(
    'ua', 'u', help='the user agent (uses `%s` ENV if available)' % api.UA_ENV,
    default=environ.get(api.UA_ENV, api.DEF_USER_AGENT))
@manager.arg(
    'chunksize_rows', 'c', help='number of rows to write at a time',
    type=int, default=api.CHUNKSIZE_ROWS)
@manager.arg(
    'chunksize_bytes', 'C', help='number of bytes to read/write at a time',
    type=int, default=api.CHUNKSIZE_BYTES)
@manager.arg('primary_key', 'p', help="Unique field(s), e.g., 'field1,field2'")
@manager.arg(
    'quiet', 'q', help='suppress debug statements', type=bool, default=False)
@manager.arg(
    'type_cast', 't', help="type cast values based on field names.",
    type=bool, default=False)
@manager.arg(
    'sanitize', 's', help='underscorify and lowercase field names', type=bool,
    default=False)
@manager.arg(
    'force', 'f', help="update resource even if it hasn't changed.",
    type=bool, default=False)
@manager.command
def update(resource_id, force=None, **kwargs):
    """Updates a datastore table based on the current filestore resource"""
    verbose = not kwargs.get('quiet')
    chunk_bytes = kwargs.get('chunk_bytes', api.CHUNKSIZE_BYTES)
    ckan_kwargs = {k: v for k, v in kwargs.items() if k in api.CKAN_KEYS}
    hash_kwargs = {'chunksize': chunk_bytes, 'verbose': verbose}

    try:
        ckan = api.CKAN(**ckan_kwargs)
        r = ckan.fetch_resource(resource_id)
        filepath = NamedTemporaryFile(delete=False).name
        write_kwargs = {
            'length': r.headers.get('content-length'),
            'chunksize': chunk_bytes
        }

        tio.write_file(filepath, r.iter_content, **write_kwargs)
    except (api.NotFound, api.NotAuthorized) as err:
        sys.stderr.write('ERROR: %s\n' % str(err))
        filepath = None
        sys.exit(1)
    except Exception as err:
        sys.stderr.write('ERROR: %s\n' % str(err))
        traceback.print_exc(file=sys.stdout)
        filepath = None
        sys.exit(1)
    else:
        try:
            old_hash = ckan.get_hash(resource_id)
        except api.NotFound as err:
            item = err.args[0]['item']

            if item == 'package':
                orgs = ckan.organization_list(permission='admin_group')
                owner_org = (
                    o['id'] for o in orgs
                    if o['display_name'] == kwargs['hash_group']).next()

                package_kwargs = {
                    'name': kwargs['hash_table'],
                    'owner_org': owner_org,
                    'package_creator': 'Hash Table',
                    'dataset_source': 'Multiple sources',
                    'notes': 'Datastore resource hash table'
                }

                ckan.hash_table_pack = ckan.package_create(**package_kwargs)

            if item in {'package', 'resource'}:
                fileobj = StringIO('datastore_id,hash\n')
                create_kwargs = {'fileobj': fileobj, 'name': api.DEF_HASH_RES}
                table = kwargs['hash_table']
                resource = ckan.create_resource(table, **create_kwargs)
                ckan.hash_table_id = resource['id']

            ckan.create_hash_table(verbose)
            old_hash = ckan.get_hash(resource_id)

        new_hash = tup.hash_file(filepath, **hash_kwargs)
        changed = new_hash != old_hash if old_hash else True

        if verbose:
            print(get_message(changed, force))

        if not (changed or force):
            sys.exit(0)

        kwargs['encoding'] = r.encoding
        kwargs['content_type'] = r.headers['content-type']
        updated = ckan.update_datastore(resource_id, filepath, **kwargs)

        if updated and verbose:
            print('Success! Resource %s updated.' % resource_id)

        if updated and changed:
            ckan.update_hash_table(resource_id, new_hash, verbose)
        elif not updated:
            sys.stderr.write('ERROR: resource %s not updated.' % resource_id)
            traceback.print_exc(file=sys.stdout)
            sys.exit(1)
    finally:
        if filepath and verbose:
            print('Removing tempfile...')

        unlink(filepath) if filepath else None


@manager.arg(
    'source', help='the source file path', nargs='?', default=sys.stdin)
@manager.arg(
    'resource_id', 'R', help='the resource id (default: source file name)')
@manager.arg(
    'encoding', 'e', help=("the file encoding (read from the file's extended "
    'attributes if uploading a file downloaded with `fs.fetch` on Mac or'
    ' Linux'), default='utf-8')
@manager.arg(
    'remote', 'r', help='the remote ckan url (uses `%s` ENV if available)' %
    api.REMOTE_ENV, default=environ.get(api.REMOTE_ENV))
@manager.arg(
    'api_key', 'k', help='the api key (uses `%s` ENV if available)' %
    api.API_KEY_ENV, default=environ.get(api.API_KEY_ENV))
@manager.arg(
    'ua', 'u', help='the user agent (uses `%s` ENV if available)' % api.UA_ENV,
    default=environ.get(api.UA_ENV))
@manager.arg(
    'chunksize_rows', 'c', help='number of rows to write at a time',
    type=int, default=api.CHUNKSIZE_ROWS)
@manager.arg('primary_key', 'p', help="Unique field(s), e.g., 'field1,field2'")
@manager.arg(
    'sanitize', 's', help='underscorify and lowercase field names', type=bool,
    default=False)
@manager.arg(
    'quiet', 'q', help='suppress debug statements', type=bool, default=False)
@manager.arg(
    'type_cast', 't', help="type cast values based on field names.",
    type=bool, default=False)
@manager.command
def upload(source, resource_id=None, **kwargs):
    """Uploads a file to a datastore table"""
    verbose = not kwargs['quiet']
    resource_id = resource_id or p.splitext(p.basename(source))[0]

    if '.' in resource_id:
        resource_id = resource_id.split('.')[0]

    ckan_kwargs = {k: v for k, v in kwargs.items() if k in api.CKAN_KEYS}

    if verbose:
        print(
            'Uploading %s to datastore resource %s...' % (source, resource_id))

    # read encoding from extended attributes
    x = xattr(source)

    try:
        kwargs['encoding'] = x.get('com.ckanutils.encoding')
    except IOError:
        pass

    if verbose and kwargs['encoding']:
        print('Using encoding %s' % kwargs['encoding'])

    try:
        ckan = api.CKAN(**ckan_kwargs)
    except Exception as err:
        sys.stderr.write('ERROR: %s\n' % str(err))
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)

    if ckan.update_datastore(resource_id, source, **kwargs):
        print('Success! Resource %s uploaded.' % resource_id)
    else:
        sys.stderr.write('ERROR: resource %s not uploaded.' % resource_id)
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)


@manager.arg(
    'resource_id', help='the resource id', nargs='?', default=sys.stdin)
@manager.arg(
    'remote', 'r', help='the remote ckan url (uses `%s` ENV if available)' %
    api.REMOTE_ENV, default=environ.get(api.REMOTE_ENV))
@manager.arg(
    'api_key', 'k', help='the api key (uses `%s` ENV if available)' %
    api.API_KEY_ENV, default=environ.get(api.API_KEY_ENV))
@manager.arg(
    'ua', 'u', help='the user agent (uses `%s` ENV if available)' % api.UA_ENV,
    default=environ.get(api.UA_ENV))
@manager.arg(
    'filters', 'f', help=('the filters to apply before deleting, e.g., {"name"'
    ': "fred"}'))
@manager.command
def delete(resource_id, **kwargs):
    """Deletes a datastore table"""
    ckan_kwargs = {k: v for k, v in kwargs.items() if k in api.CKAN_KEYS}

    try:
        ckan = api.CKAN(**ckan_kwargs)
        ckan.delete_table(resource_id, filters=kwargs.get('filters'))
    except Exception as err:
        sys.stderr.write('ERROR: %s\n' % str(err))
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)


if __name__ == '__main__':
    manager.main()
