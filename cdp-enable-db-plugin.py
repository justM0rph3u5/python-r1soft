#!/usr/bin/env

#!/usr/bin/env python

import suds.client
import logging

logger = logging.getLogger('cdp-add-agent')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)
logger.propagate = False

class MetaClient(object):
    def __init__(self, url_base, **kwargs):
        self.__url_base = url_base
        self.__init_args = kwargs
        self.__clients = dict()

    def __getattr__(self, name):
        c = self.__clients.get(name, None)
        logger.debug('Accessing SOAP client: %s' % name)
        if c is None:
            logger.debug('Client doesn\'t exist, creating: %s' % name)
            c = suds.client.Client(self.__url_base % name, **self.__init_args)
            self.__clients[name] = c
        return c

def get_wsdl_url(hostname, namespace, use_ssl=True, port_override=None):
    if use_ssl:
        proto = 'https'
    else:
        proto = 'http'
    if port_override is None:
        if use_ssl:
            port = 9443
        else:
            port = 9080
    else:
        port = port_override
    url = '%s://%s:%d/%s?wsdl' % (proto, hostname, port, namespace)
    logging.debug('Creating WSDL URL: %s' % url)
    return url

if __name__ == '__main__':
    import sys
    import re

    cdphost = sys.argv[1]
    cdpuser, cdppass = sys.argv[2].split(':')
    sqluser, sqlpass = sys.argv[3].split(':')

    client = MetaClient(get_wsdl_url(cdphost, '%s'),
        username=cdpuser, password=cdppass)

    db_cand_pattern = re.compile('mce\d+-db|(?:obp|sip)(?:uk)?4-\d+')

    logger.info('Getting list of agents')
    agents = client.Agent.service.getAgents()
    logger.info('Getting list of disk safes')
    disksafes = client.DiskSafe.service.getDiskSafes()
    logger.info('Getting list of policies')
    policies = client.Policy2.service.getPolicies()

    for agent in agents:
        logger.info('> Considering agent %s (%s)', agent.hostname, agent.description)
        if db_cand_pattern.match(agent.hostname) or \
                db_cand_pattern.match(agent.description):
            logger.info('=> Agent looks like a good candidate for db plugin: %s',
                agent.hostname)
            if agent.databaseAddOnEnabled:
                logger.info('==> Agent already has db plugin enabled')
            else:
                logger.info('==> Enabling db plugin for agent')
                agent.databaseAddOnEnabled = True
                #client.Agent.service.updateAgent(agent)
                logger.debug('*** Enabled db plugin ***')
            logger.info('=> Finding disksafes for agent')
            agent_ds = [d for d in disksafes if d.agentID == agent.id]
            logger.debug('=> Found %d disksafe(s)', len(agent_ds))
            logger.info('=> Finding policy for agent')
            policy = [p for p in policies if p.diskSafeID in [d.id for d in agent_ds]][0]
            logger.debug('=> Found policy %s (%s)', policy.name, policy.id)
            try:
                dbi_count = len(policy.databaseInstanceList)
            except AttributeError as e:
                logger.warn('!! Does not look like agent has db plugin enabled: %s !!', e)
            else:
                if dbi_count > 0:
                    logger.info('==> Policy already has %d database instances',
                        len(policy.databaseInstanceList))
                else:
                    logger.info('==> Policy has no database instances, creating one')
                    dbi = client.Policy2.factory.create('databaseInstance')
                    dbi.advancedOptions.entry.append({
                            'DO_TABLE_STATS_OPTION': False
                        })
                    dbi.dataBaseType = client.Policy2.factory.create('dataBaseType').MYSQL
                    dbi.enabled = True
                    dbi.hostname = '127.0.0.1'
                    dbi.name = 'default'
                    dbi.username = sqluser
                    dbi.password = sqlpass
                    dbi.portNumber = 3306
                    dbi.useAlternateDataDirectory = False
                    dbi.useAlternateHostname = True
                    dbi.useAlternateInstallDirectory = False
                    logger.info('==> Adding database instance to policy')
                    #policy.databaseInstanceList.append(dbi)
                    logger.debug('*** Added database instance to policy ***')
            if policy.state != 'OK':
                logger.warn('!! Policy (%s/%s) is not OK !!', policy.name, policy.description)
