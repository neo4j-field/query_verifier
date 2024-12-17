# Neo4j Query Verifier

## Intent

This project is designed to help validate queries from a `query.log` file against a specific Neo4j version.

If you need to upgrade from version X to version Y and want to ensure all your queries remain valid, you can generate a query log in version X and then run this script against version Y, using the query log from the previous version as input.

## Setup

First, install the requirements by running:

```bash
pip install -r requirements.txt
```

### Driver

Ensure you use the driver version that corresponds to the Neo4j version you're testing against. Set it in the `requirements.txt` file.

## Usage

##Options

- `--input-path <path>` : path to either a Neo4j query.log file, a directory containing query.log files, or a single-column CSV file containing a list of cypher queries (for example `all_queries.csv` exported by the healthcheck).
- `--output-path <path>` : directory where the results are written to.
- Optional `--query-log-bolt-port <path>` : BOLT port of the server that executed the queries (defaults to 7687). Make sure it matches, so that the query.log files can be parsed (if query.log(s) are specified as input).
- Optional `--neo4j-target-version <path>` : docker image tag of the `neo4j` image to test against. Defaults to `5-enterprise`. Refer to https://hub.docker.com/_/neo4j for the list of available images.


As an alternative to using `--neo4j-target-version`, you can provide connection details to an already running Ne4oj instance to test against :
- `--uri <uri>` : neo4j URI (ex: neo4j://host:7687)
- `--username <name>` : username of the user used to cnnect to that existing neo4j server
- `--password <pwd>` : password of that user


## Local Neo4j Instance

If you have a running Neo4j instance you want to test against, use the following command:

```bash
python3 query-verifier.py --input-path=$QUERY_LOGS_PATH --output-path=$RESULT_OUTPUT_PATH --uri=$NEO4J_URI --username=$NEO4J_USERNAME --password=$NEO4J_PASSWORD
```

## Docker Neo4j Instance

You can validate against any Neo4j version by choosing the version to run as a Docker container:

```bash
python3 query-verifier.py --input-path=$QUERY_LOGS_PATH --output-path=$RESULT_OUTPUT_PATH --neo4j-target-version=5.19.0-enterprise
```

## Execution Results

Imagine your query log contains the following query, which is deprecated in version 5.19:

```plaintext
2024-05-17 08:54:50.493+0000 INFO  0 ms: (planning: 0, waiting: 0) - 7818 page hits, 0 page faults - bolt-session bolt neo4j-java/4.4.11-7d3fdc18543dae49c0c337b2885771b4f38a288d client/172.18.0.6:58674 server/172.18.0.4:7687> - RETURN 1 as my\u0085identifier - {currentId: '4b640479-63be-4e94-9b9b-53f23e9fb53a'} - {}
2024-05-17 08:54:50.493+0000 INFO  0 ms: (planning: 0, waiting: 0) - 7818 page hits, 0 page faults - bolt-session bolt neo4j-java/4.4.11-7d3fdc18543dae49c0c337b2885771b4f38a288d client/172.18.0.6:58674 server/172.18.0.4:7687> - SHOW EXISTS CONSTRAINTS - {currentId: '4b640479-63be-4e94-9b9b-53f23e9fb53a'} - {}
```

If you run it against a version earlier than 5.19, the output should be an empty file with only one header:

```plaintext
query,category,message
```

Otherwise, if you run it against version 5.19 or later, you might see something like this:

```plaintext
query,category,message
RETURN 1 as my\u0085identifier,DEPRECATION,"The Unicode character `\u0085` is deprecated for unescaped identifiers and will be considered as a whitespace character in the future. To continue using it, escape the identifier by adding backticks around the identifier `myidentifier`."
SHOW EXISTS CONSTRAINTS,Statement,"`SHOW CONSTRAINTS` no longer allows the `EXISTS` keyword, please use `EXIST` or `PROPERTY EXISTENCE` instead. (line 1, column 9 (offset: 8))
""EXPLAIN SHOW EXISTS CONSTRAINTS""
```