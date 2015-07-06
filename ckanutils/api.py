# -*- coding: utf-8 -*-
# vim: sw=4:ts=4:expandtab

"""
ckanutils.api
~~~~~~~~~~~~~

Provides methods for interacting with a CKAN instance

Examples:
    literal blocks::

        python example_google.py

Attributes:
    CKAN_KEYS (List[str]): available CKAN keyword arguments.
"""

from __future__ import (
    absolute_import, division, print_function, with_statement,
    unicode_literals)

import requests
import ckanapi

from os import environ, path as p
from . import utils, __version__ as version
from ckanapi import NotFound

CKAN_KEYS = ['hash_table', 'remote', 'api_key', 'ua', 'force', 'quiet']
API_KEY_ENV = 'CKAN_API_KEY'
REMOTE_ENV = 'CKAN_REMOTE_URL'
UA_ENV = 'CKAN_USER_AGENT'
DEF_USER_AGENT = 'ckanutils/%s' % version
DEF_HASH_TABLE = 'hash-table'
CHUNKSIZE_ROWS = 10 ** 3
CHUNKSIZE_BYTES = 2 ** 20


class CKAN(object):
    """Interacts with a CKAN instance.

    Attributes:
        force (bool): Force.
        verbose (bool): Print debug statements.
        quiet (bool): Suppress debug statements.
        address (str): CKAN url.
        hash_table (str): The hash table package id.
        keys (List[str]):
    """

    def __init__(self, **kwargs):
        """Initialization method.

        Args:
            **kwargs: Keyword arguments.

        Kwargs:
            hash_table (str): The hash table package id.
            remote (str): The remote ckan url.
            api_key (str): The ckan api key.
            ua (str): The user agent.
            force (bool): Force (default: True).
            quiet (bool): Suppress debug statements (default: False).

        Returns:
            New instance of :class:`CKAN`

        Examples:
            >>> CKAN()  #doctest: +ELLIPSIS
            <ckanutils.api.CKAN object at 0x...>
        """
        default_ua = environ.get(UA_ENV, DEF_USER_AGENT)
        def_remote = environ.get(REMOTE_ENV)
        def_api_key = environ.get(API_KEY_ENV)
        remote = kwargs.get('remote', def_remote)

        self.api_key = kwargs.get('api_key', def_api_key)
        self.force = kwargs.get('force', True)
        self.quiet = kwargs.get('quiet')
        self.user_agent = kwargs.get('ua', default_ua)
        self.verbose = not self.quiet
        self.hash_table = kwargs.get('hash_table', DEF_HASH_TABLE)

        ckan_kwargs = {'apikey': self.api_key, 'user_agent': self.user_agent}
        attr = 'RemoteCKAN' if remote else 'LocalCKAN'
        ckan = getattr(ckanapi, attr)(remote, **ckan_kwargs)

        self.address = ckan.address

        try:
            self.hash_table_pack = ckan.action.package_show(id=self.hash_table)
        except NotFound:
            self.hash_table_pack = None

        try:
            self.hash_table_id = self.hash_table_pack['resources'][0]['id']
        except (IndexError, TypeError):
            self.hash_table_id = None

        # shortcuts
        self.datastore_search = ckan.action.datastore_search
        self.datastore_create = ckan.action.datastore_create
        self.datastore_delete = ckan.action.datastore_delete
        self.datastore_upsert = ckan.action.datastore_upsert
        self.datastore_search = ckan.action.datastore_search
        self.resource_show = ckan.action.resource_show
        self.resource_create = ckan.action.resource_create
        self.revision_show = ckan.action.revision_show

    def create_table(self, resource_id, fields, **kwargs):
        """Creates a datastore table for an existing filestore resource.

        Args:
            resource_id (str): The filestore resource id.
            fields (List[dict]): fields/columns and their extra metadata.
            **kwargs: Keyword arguments that are passed to datastore_create.

        Kwargs:
            force (bool): Create resource even if read-only.
            aliases (List[str]): name(s) for read only alias(es) of the
                resource.
            primary_key (List[str]): field(s) that represent a unique key.
            indexes (List[str]): index(es) on table.

        Returns:
            dict: The newly created data object.

        Raises:
            ValidationError: If unable to validate user on ckan site.
            NotFound: If unable to find resource.

        Examples:
        >>> CKAN(quiet=True).create_table('rid', fields=[{'id': 'field', \
'type': 'text'}])
        Traceback (most recent call last):
        NotFound: Resource "rid" was not found.
        """
        kwargs.setdefault('force', self.force)
        kwargs['resource_id'] = resource_id
        kwargs['fields'] = fields

        if self.verbose:
            print('Creating table `%s` in datastore...' % resource_id)

        try:
            return self.datastore_create(**kwargs)
        except ckanapi.ValidationError as err:
            if err.error_dict.get('resource_id') == [u'Not found: Resource']:
                raise NotFound(
                    'Resource `%s` was not found in filestore.' % resource_id)
            else:
                raise

    def delete_table(self, resource_id, **kwargs):
        """Deletes a datastore table.

        Args:
            resource_id (str): The datastore resource id.
            **kwargs: Keyword arguments that are passed to datastore_create.

        Kwargs:
            force (bool): Delete resource even if read-only.
            filters (dict): Filters to apply before deleting, e.g.,
                {"name": "fred"}. If missing delete whole table and all
                dependent views.

        Returns:
            dict: Original filters sent if table was found, `None` otherwise.

        Raises:
            ValidationError: If unable to validate user on ckan site.

        Examples:
            >>> CKAN(quiet=True).delete_table('rid')
        """
        kwargs.setdefault('force', self.force)
        kwargs['resource_id'] = resource_id

        if self.verbose:
            print('Deleting table `%s` from datastore...' % resource_id)

        try:
            result = self.datastore_delete(**kwargs)
        except NotFound:
            result = None

            if self.verbose:
                print(
                    "Can't delete. Table `%s` was not found in datastore." %
                    resource_id)
        except ckanapi.ValidationError as err:
            if 'read-only' in err.error_dict:
                print(
                    "Can't delete. Datastore table is read only. Set "
                    "'force' to True and try again.")

                result = None

        return result

    def insert_records(self, resource_id, records, **kwargs):
        """Inserts records into a datastore table.

        Args:
            resource_id (str): The datastore resource id.
            records (List[dict]): The records to insert.
            **kwargs: Keyword arguments that are passed to datastore_create.

        Kwargs:
            method (str): Insert method. One of ['update, 'insert', 'upsert']
                (default: 'insert').
            force (bool): Create resource even if read-only.
            start (int): Row number to start from (zero indexed).
            stop (int): Row number to stop at (zero indexed).
            chunksize (int): Number of rows to write at a time.

        Returns:
            int: Number of records inserted.

        Raises:
            NotFound: If unable to find the resource.

        Examples:
            >>> CKAN(quiet=True).insert_records('rid', [{'field': 'value'}])
            Traceback (most recent call last):
            NotFound: Resource "rid" was not found.
        """
        chunksize = kwargs.pop('chunksize', 0)
        start = kwargs.pop('start', 0)
        stop = kwargs.pop('stop', None)

        kwargs.setdefault('force', self.force)
        kwargs.setdefault('method', 'insert')
        kwargs['resource_id'] = resource_id
        count = 1

        for chunk in utils.chunk(records, chunksize, start=start, stop=stop):
            length = len(chunk)

            if self.verbose:
                print(
                    'Adding records %i - %i to resource %s...' % (
                        count, count + length - 1, resource_id))

            kwargs['records'] = chunk

            try:
                self.datastore_upsert(**kwargs)
            except requests.exceptions.ConnectionError as err:
                if 'Broken pipe' in err.message[1]:
                    print('Chunksize too large. Try using a smaller chunksize.')
                    return 0
                else:
                    raise err
            count += length

        return count

    def get_hash(self, resource_id):
        """Gets the hash of a datastore table.

        Args:
            resource_id (str): The datastore resource id.

        Returns:
            str: The datastore resource hash.

        Raises:
            NotFound: If `hash_table_id` isn't set or not in datastore.
            NotAuthorized: If unable to authorize ckan user.

        Examples:
            >>> CKAN(hash_table='hash').get_hash('rid')
            Traceback (most recent call last):
            NotFound: `hash_table_id` not set!
            >>> CKAN(quiet=True).get_hash('rid')
        """
        if not self.hash_table_pack:
            message = 'No hash table package found!'
            raise NotFound({'message': message, 'item': 'package'})

        if not self.hash_table_id:
            message = 'No hash table resource found!'
            raise NotFound({'message': message, 'item': 'resource'})

        kwargs = {
            'resource_id': self.hash_table_id,
            'filters': {'datastore_id': resource_id},
            'fields': 'hash',
            'limit': 1
        }

        try:
            result = self.datastore_search(**kwargs)
            resource_hash = result['records'][0]['hash']
        except NotFound:
            message = (
                'Hash table `%s` was not found in datastore!' %
                self.hash_table_id)

            raise NotFound({'message': message, 'item': 'datastore'})
        except IndexError:
            if self.verbose:
                print('Resource `%s` was not found in hash table.' % resource_id)

            resource_hash = None

        if self.verbose:
            print('Resource `%s` hash is `%s`.' % (resource_id, resource_hash))

        return resource_hash

    def fetch_resource(self, resource_id, **kwargs):
        """Fetches a single resource from filestore.

        Args:
            resource_id (str): The filestore resource id.
            **kwargs: Keyword arguments that are passed to datastore_create.

        Kwargs:
            filepath (str): Output file path or directory.
            name_from_id (bool): Use resource id for filename.
            chunksize (int): Number of bytes to write at a time.
            user_agent (str): The user agent.

        Returns:
            Tuple(obj, str): Tuple of (requests.Response object, filepath).

        Raises:
            NotFound: If unable to find the resource.

        Examples:
            >>> CKAN(quiet=True).fetch_resource('rid')
            Traceback (most recent call last):
            NotFound: Resource "rid" was not found.
        """
        user_agent = kwargs.pop('user_agent', self.user_agent)
        filepath = kwargs.pop('filepath', utils.get_temp_filepath())
        name_from_id = kwargs.pop('name_from_id', False)
        isdir = p.isdir(filepath)

        try:
            resource = self.resource_show(id=resource_id)
        except NotFound:
            # Keep exception message consistent with the others
            raise NotFound(
                'Resource `%s` was not found in filestore.' % resource_id)

        url = resource['perma_link']

        if self.verbose:
            print('Downloading url %s...' % url)

        headers = {'User-Agent': user_agent}
        r = requests.get(url, stream=True, headers=headers)
        h = r.headers

        if isdir and not name_from_id:
            try:
                filename = h['content-disposition'].split('=')[1].split('"')[1]
            except (KeyError, IndexError) as e:
                filename = p.basename(url)
        elif isdir:
            filename = resource_id

        if isdir and filename.startswith('export?format='):
            filename = '%s.%s' % (resource_id, filename.split('=')[1])
        elif isdir and '.' not in filename:
            filename = '%s.%s' % (filename, utils.ctype2ext(h['content-type']))

        if isdir:
            filepath = p.join(filepath, filename)

        utils.write_file(filepath, r, **kwargs)
        return (r, filepath)

    def _update_resource(self, resource, message, **kwargs):
        """Helps create or update a single resource on filestore.
        To create a resource, you must supply either `url`, `filepath`, or
        `fileobj`.

        Args:
            resource (dict): The resource passed to resource_create.
            **kwargs: Keyword arguments that are passed to resource_create.

        Kwargs:
            url (str): New file url (for file link).
            fileobj (obj): New file like object (for file upload).
            filepath (str): New file path (for file upload).
            post (bool): Post data using requests instead of ckanapi.
            name (str): The resource name.
            description (str): The resource description.
            hash (str): The resource hash.

        Returns:
            obj: requests.Response object if `post` option is specified,
                ckan resource object otherwise.

        Examples:
            >>> ckan = CKAN(quiet=True)
            >>> url = 'http://example.com/file'
            >>> resource = {'package_id': 'pid', 'url': url}
            >>> message = 'Creating new resource...'
            >>> ckan._update_resource(resource, message)
            Package "pid" was not found.
            >>> resource.update({'resource_id': 'rid', 'name': 'name'})
            >>> resource.update({'description': 'description', 'hash': 'hash'})
            >>> message = 'Updating resource...'
            >>> ckan._update_resource(resource, message)
            Resource "rid" was not found.
        """
        post = kwargs.pop('post', None)
        filepath = kwargs.pop('filepath', None)
        fileobj = kwargs.pop('fileobj', None)
        f = open(filepath, 'rb') if filepath else fileobj
        resource.update(kwargs)

        if self.verbose:
            print(message)

        if post:
            url = '%s/api/action/resource_create' % self.address
            hdrs = {
                'X-CKAN-API-Key': self.api_key, 'User-Agent': self.user_agent}

            data = {'data': resource, 'headers': hdrs}
            data.update({'files': {'upload': f}}) if f else None
        else:
            resource.update({'upload': f}) if f else None
            data = {
                k: v for k, v in resource.items() if not isinstance(v, dict)}

        try:
            if post:
                r = requests.post(url, **data)
            else:
                r = self.resource_create(**data)
        except NotFound:
            # Keep exception message consistent with the others
            if 'resource_id' in resource:
                print(
                    'Resource `%s` was not found in filestore.' %
                    resource['resource_id'])
            else:
                print(
                    'Package `%s` was not found in filestore.' %
                    resource['package_id'])

            return None
        except requests.exceptions.ConnectionError as err:
            if 'Broken pipe' in err.message[1]:
                print('File size too large. Try uploading a smaller file.')
                r = None
            else:
                raise err
        finally:
            f.close() if f else None

        return r

    def create_resource(self, package_id, **kwargs):
        """Creates a single resource on filestore. You must supply either
        `url`, `filepath`, or `fileobj`.

        Args:
            package_id (str): The filestore package id.
            **kwargs: Keyword arguments that are passed to resource_create.

        Kwargs:
            url (str): New file url (for file link).
            filepath (str): New file path (for file upload).
            fileobj (obj): New file like object (for file upload).
            post (bool): Post data using requests instead of ckanapi.
            name (str): The resource name (defaults to the filename).
            description (str): The resource description.
            hash (str): The resource hash.

        Returns:
            obj: requests.Response object if `post` option is specified,
                ckan resource object otherwise.

        Raises:
            TypeError: If neither `url`, `filepath`, nor `fileobj` are supplied.

        Examples:
            >>> ckan = CKAN(quiet=True)
            >>> ckan.create_resource('pid')
            Traceback (most recent call last):
            TypeError: You must specify either a `url` or `filepath`
            >>> ckan.create_resource('pid', url='http://example.com/file')
            Package "pid" was not found.
        """
        if not {'url', 'filepath', 'fileobj'}.intersection(kwargs.keys()):
            raise TypeError(
                'You must specify either a `url`, `filepath`, or `fileobj`')

        path = kwargs.get('url') or kwargs.get('filepath')
        kwargs['name'] = kwargs.get('name', p.basename(path))
        kwargs['format'] = p.splitext(path)[1]
        resource = {'package_id': package_id}
        message = 'Creating new resource in package %s...' % package_id
        return self._update_resource(resource, message, **kwargs)

    def update_resource(self, resource_id, **kwargs):
        """Updates a single resource on filestore.

        Args:
            resource_id (str): The filestore resource id.
            **kwargs: Keyword arguments that are passed to resource_create.

        Kwargs:
            url (str): New file url (for file link).
            filepath (str): New file path (for file upload).
            fileobj (obj): New file like object (for file upload).
            post (bool): Post data using requests instead of ckanapi.
            name (str): The resource name.
            description (str): The resource description.
            hash (str): The resource hash.

        Returns:
            obj: requests.Response object if `post` option is specified,
                ckan resource object otherwise.

        Examples:
            >>> CKAN(quiet=True).update_resource('rid')
            Resource "rid" was not found.
            False
        """
        try:
            resource = self.resource_show(id=resource_id)
        except NotFound:
            # Keep exception message consistent with the others
            print('Resource `%s` was not found in filestore.' % resource_id)
            return None

        resource['package_id'] = self.get_package_id(resource_id)
        message = 'Updating resource %s...' % resource_id
        return self._update_resource(resource, message, **kwargs)

    def get_package_id(self, resource_id):
        """Gets the package id of a single resource on filestore.

        Args:
            resource_id (str): The filestore resource id.

        Returns:
            str: The package id.

        Examples:
            >>> CKAN(quiet=True).get_package_id('rid')
            Resource "rid" was not found.
        """
        try:
            resource = self.resource_show(id=resource_id)
        except NotFound:
            # Keep exception message consistent with the others
            print('Resource `%s` was not found in filestore.' % resource_id)
            return None
        else:
            revision = self.revision_show(id=resource['revision_id'])
            return revision['packages'][0]
