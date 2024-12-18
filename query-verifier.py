import click
import re
import csv
import json
from neo4j import GraphDatabase
import neo4j
import re
import os
from os.path import isfile, join
import docker
import time
from datetime import datetime

IGNORE_LIST = ['Neo.ClientNotification.Statement.UnknownPropertyKeyWarning',
               'Neo.ClientNotification.Statement.ParameterNotProvided',
               'Neo.ClientError.Statement.ParameterMissing',
               'Neo.ClientNotification.Statement.UnknownRelationshipTypeWarning',
               'Neo.ClientNotification.Statement.UnknownLabelWarning',
               'Neo.ClientNotification.Schema.HintedIndexNotFound']

@click.group
def cli():
    pass

@cli.command()
@click.option('--input-path', required=True, help='Import path : either directory containing query.log files, or CSV file containing list of queries')
@click.option('--output-path', required=True, help='Output path for verified files')
@click.option('--query-log-bolt-port', required=True, default= '7687', help='The BOLT port found in the query.log file')
@click.option('--uri', help='Neo4j URI instance')
@click.option('--username', help='Neo4j URI username')
@click.option('--password', help='Neo4j URI password')
@click.option('--neo4j-target-version', default='5-enterprise', help='Neo4j target version (docker image tag)')
def verify_queries_and_generate_reports(input_path, output_path, query_log_bolt_port, uri, username, password, neo4j_target_version):

    mode = determine_mode(input_path)
    os.makedirs(output_path, exist_ok=True)

    try:
        neo4j_uri=uri
        neo4j_username=username
        neo4j_password=password

        container = None
        if (neo4j_target_version and not uri):
            print(f"No existing neo4j server details provided. Starting a new one locally in docker...")
            neo4j_uri="bolt://127.0.0.1:17687"
            neo4j_username="neo4j"
            neo4j_password="admin1234"
            container = start_container(neo4j_target_version, neo4j_username, neo4j_password, neo4j_uri)

        if mode == "log_dir":
            all_queries = read_queries(input_path, query_log_bolt_port)
        elif mode == "csv":
            with open(input_path, 'r', newline='', encoding='utf-8') as csvfile:
                all_queries = [row[0] for row in csv.reader(csvfile) if row]
        elif mode == "log":
            all_queries = read_query_file(input_path, query_log_bolt_port)


        print(f"Testing queries against {neo4j_uri}...")
        failed_queries, deprecated_queries = execute_queries(all_queries, neo4j_username, neo4j_password, neo4j_uri)

        #build timestmap to the second
        timestamp=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        write_output(output_path, f"deprecated_queries_{timestamp}.csv", deprecated_queries)
        write_output(output_path, f"failed_queries_{timestamp}.csv", failed_queries)


        if container is not None:
            container.kill()

    finally:
        if container is not None:
            container.remove(force=True)

def determine_mode(input_path):
    mode=""
    if os.path.isdir(input_path):
        mode = "log_dir"
    elif os.path.isfile(input_path):
        # Extract file extension
        _, extension = os.path.splitext(input_path)
        if extension == ".csv":
            mode = "csv"
        elif extension == ".log":
            mode = "log"
    else:
        click.echo("Error: Could not determine the content of --input-path value.")
        exit(1)
    print(f"Input mode: {mode}")
    return mode

def start_container(neo4j_target_version, neo4j_username, neo4j_password, neo4j_uri):
    bolt_port=neo4j_uri.split(":")[2]
    client = docker.from_env()
    docker_image=f'neo4j:{neo4j_target_version}'
    if neo4j_target_version.startswith("4"):
        plugins='["apoc","graph-data-science", "n10s"]'
    else:
        plugins='["apoc","apoc-extended","graph-data-science", "n10s"]'
    print(f"Pulling docker image {docker_image}...")
    client.images.pull(docker_image)
    print(f"Running docker container from image {docker_image}...")
    container = client.api.create_container(
        image=docker_image,
        environment=["NEO4J_ACCEPT_LICENSE_AGREEMENT=yes", 
                     f"NEO4J_AUTH={neo4j_username}/{neo4j_password}",
                     f'NEO4J_PLUGINS={plugins}'
                    ],
        ports={"7687/tcp": {}, "7474/tcp": {}},
        host_config=client.api.create_host_config(port_bindings={
            "7687/tcp": ('127.0.0.1', bolt_port),
            "7474/tcp": ('127.0.0.1', 17474)
        }),
        healthcheck={
            "Test": ["CMD-SHELL", "wget -q --spider http://localhost:7474 || exit 1"],
            "Interval": 30000000000,  # 30 seconds in nanoseconds
            "Timeout": 20000000000,   # 20 seconds in nanoseconds
            "Retries": 10,
            "StartPeriod": 60000000000  # 60 seconds in nanoseconds
        },
        name="query_verifier"
    )
    
    client.api.start(container['Id'])
    container = client.containers.get(container['Id'])

    try:
        wait_for_container_healthy(container)
    except TimeoutError as e:
        print(e)
    return container

def wait_for_container_healthy(container, timeout=300):
    start_time = time.time()
    while time.time() - start_time < timeout:
        container.reload()
        health_status = container.attrs['State']['Health']['Status']
        print(f'Waiting for container to be "healthy", current state is: "{health_status}"')
        if health_status == "healthy":
            print("Container is healthy")
            return
        elif health_status == "unhealthy":
            # Print logs for debugging
            logs = container.logs().decode('utf-8')
            print(logs)
            raise RuntimeError("Container is unhealthy")
        time.sleep(5)
    raise TimeoutError("Container did not become healthy in time")

def detect_format(file_path):
    with open(file_path, 'r') as file:
        for first_line in file:
            ts_pattern = re.compile("^\\d{4}-\\d{2}-\\d{2}\\s\\d{2}:\\d{2}:\\d{2}")
            if re.search(ts_pattern, first_line):
                return "STD"
            elif first_line.startswith("{"):
                return "JSON"
            break
    return "unknown"

def read_queries(input_path, query_log_bolt_port):
    all_queries = set()
    #TODO : better regex
    # Make sure to change the pattern to match the BOLT port in your logs
    log_format = f"{query_log_bolt_port}>\\s*[^ ]+\\s*-\\s*[^ ]+\\s+-\\s*(.*?)\\s*-\\s*{{"
    pattern = re.compile(log_format)

    #parsing queries
    print(f"Parsing query logs from {input_path}...")
    files = [f for f in os.listdir(input_path) if isfile(join(input_path, f)) and f.startswith("query")]
    print(files)
    for log in sorted(files):
        queries = read_query_file(join(input_path, log), query_log_bolt_port)
        all_queries.update(queries)
    print(f"Parsed a total of {len(all_queries)} distinct queries")
    return all_queries

def read_query_file(log, query_log_bolt_port):
    queries = set()
    log_format = f"{query_log_bolt_port}>\\s*[^ ]+\\s*-\\s*[^ ]+\\s+-\\s*(.*?)\\s*-\\s*{{"
    pattern = re.compile(log_format)
    format = detect_format(log)
    print(f"Reading {log} [{format}]...")
    with open(log, 'r') as input_file:
        for row in input_file:
            if format == "STD":
                #TODO : deal with multiline queries
                #TODO : filter out 'Transaction started', 'Transaction committed', "Transaction rolled back" events and "Query started" events
                match = re.search(pattern, row)
                if match:
                    result = match.group(1).strip()
                    #set : don't store duplicate queries
                    queries.add(result)
            elif format == "JSON":
                dict = json.loads(row)
                if "query" in dict:
                    queries.add(dict["query"])
            #TODO : aggregate client/driver label + source IP information in order to help find the emitter
    print(f"Parsed {len(queries)} distinct queries")
    return queries

def execute_queries(all_queries, neo4j_username, neo4j_password, neo4j_uri):
    with GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password)) as driver:
        driver.verify_connectivity()
        failed_queries = []
        deprecated_queries = []
        i=0
        for query in all_queries:
            if not query.startswith("EXPLAIN ") and not query.startswith("PROFILE "):
                try:
                    #print(f"Testing query '{query}'...")
                    records, summary, keys = driver.execute_query("EXPLAIN " + query)
                    if summary.notifications:
                        for notif in summary.notifications:
                            if notif['code'] not in IGNORE_LIST: #TODO: filter on category DEPRECATION
                                #TODO: deal with v4 (no category)
                                #TODO: add title + severity to output
                                #v4  {  'severity': 'WARNING', 
                                #       'description': 'Did not supply query with enough parameters. The produced query plan will not be cached and is not executable without EXPLAIN. (Missing parameters: name)', 
                                #       'code': 'Neo.ClientError.Statement.ParameterMissing', 
                                #       'title': 'The statement refers to a parameter that was not provided in the request.'
                                #    }
                                category=notif['category'] if 'category' in notif else "N/A"
                                print(f"Found deprecated cypher : [{notif['code']}] {category} - {notif['description']}")
                                deprecated_queries.append({'query': query, 'category': category, 'message': notif['description']})
                except neo4j.exceptions.ClientError as e:
                    failed_queries.append({'query': query, 'category': e.category, 'message': e.message})
                i+=1
                if i % 1000 == 0:
                    print(f"{i} queries tested")
        print(f"All queried tested")
    return failed_queries, deprecated_queries

def write_output(output_path, output_file_name, output):
    print(f"Writing output to {output_path}/{output_file_name}")
    with open(output_path+'/'+output_file_name, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, ['query', 'category', 'message'])
        dict_writer.writeheader()
        dict_writer.writerows(output)

if __name__ == '__main__':
    try:
        verify_queries_and_generate_reports()
    except click.exceptions.MissingParameter as e:
        # Handle missing parameters
        click.echo(f'Missing parameter: {e.param}')