# Neo4j query verifier

## Intent

This project aims to help validate queries from a `query.log` file against a given Neo4j version.


Imagine that you need to upgrade from version X to Y but you aren't sure if all your queries are still valid in later version, all you'll need to do is generate a query log in version X, then run the script against verion Y, using the query.log of previous version as input.

## Usage

Start first by installing the requirements by running:

```
pip install -r requirements.txt
```

Then simply run

```
python3 query-verifier.py --input-path=$QUERY_LOGS_PATH --output-path=$RESULT_OUTPUT_PATH --uri=$NEO4J_URI --username=$NEO4J_USERNAME --password=$NEO4J_PASSWORD
```

The output should be an empty file with only one header if everything is fine:

```
query,category,message
```

Otherwise:

```
query,category,message
"MATCH a1:Country) WHERE a1.id = $currentId SET a1 += {alpha3:$propval0,DisabledComment:$propval1,alpha2:$propval2,Disabled:$propval3,Status:$propval4,DocumentFilter:$propval5,FamilyCode:$propval6,RiskValues:$propval7,HasCities:$propval8,Name:$propval9,Category:$propval10} RETURN a1",Statement,"Invalid input 'a1': expected ""("", ""ALL"", ""ANY"" or ""SHORTEST"" (line 1, column 15 (offset: 14))
""EXPLAIN MATCH a1:Country) WHERE a1.id = $currentId SET a1 += {alpha3:$propval0,DisabledComment:$propval1,alpha2:$propval2,Disabled:$propval3,Status:$propval4,DocumentFilter:$propval5,FamilyCode:$propval6,RiskValues:$propval7,HasCities:$propval8,Name:$propval9,Category:$propval10} RETURN a1""
               ^"
```