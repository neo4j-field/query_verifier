import click
import re
import csv
from neo4j import GraphDatabase
import neo4j
import re
import os
from os.path import isfile, join

IGNORE_LIST = ['Neo.ClientNotification.Statement.UnknownPropertyKeyWarning',
               'Neo.ClientNotification.Statement.ParameterNotProvided',
               'Neo.ClientNotification.Statement.UnknownRelationshipTypeWarning',
               'Neo.ClientNotification.Statement.UnknownLabelWarning',
               'Neo.ClientNotification.Schema.HintedIndexNotFound']

@click.group
def cli():
    pass

@cli.command()
@click.option('--input-path', required=True, help='Import path for query.log files')
@click.option('--output-path', required=True, help='Output path for verified files')
@click.option('--uri', required=True, help='Neo4j URI instance')
@click.option('--username', required=True, help='Neo4j URI username')
@click.option('--password', default='eu-north-1', help='Neo4j URI password')
def verify_queries_and_generate_reports(input_path, output_path, uri, username, password):
    files = [f for f in os.listdir(input_path) if isfile(join(input_path, f))]
    for log in files:
        queries = []
        # Make sure to change the pattern to match the BOLT port in your logs
        regex = r'7687>\s*-\s*(.*?)\s*-\s*{'
        pattern = re.compile(regex)
        print(log)
        with open(join(input_path, log), 'r') as input_file:
            for row in input_file:
                match = re.search(pattern, row)
                if match:
                    result = match.group(1).strip()
                    queries.append(result)


        bad_queries = []
        with GraphDatabase.driver(uri, auth=(username, password)) as driver:
            for query in queries:
                try:
                    records, summary, keys = driver.execute_query("EXPLAIN " + query)
                    if summary.notifications:
                        for notif in summary.notifications:
                            if notif['code'] not in IGNORE_LIST:
                                bad_queries.append({'query': query, 'category': notif['category'], 'message': notif['description']})
                except neo4j.exceptions.ClientError as e:
                    bad_queries.append({'query': query, 'category': e.category, 'message': e.message})

        with open(output_path+'/'+log, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, ['query', 'category', 'message'])
            dict_writer.writeheader()
            dict_writer.writerows(bad_queries)


if __name__ == '__main__':
    try:
        verify_queries_and_generate_reports()
    except click.exceptions.MissingParameter as e:
        # Handle missing parameters
        click.echo(f'Missing parameter: {e.param}')