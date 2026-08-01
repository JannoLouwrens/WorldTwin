import sys

path = sys.argv[1]
with open(path, "r") as f:
    cf = f.read()

if "/v1/*" in cf:
    print("v1 route already present")
    sys.exit(0)

# Insert /v1/* route before the final handle {}
v1_route = """    handle /v1/cache/* {
        uri strip_prefix /v1/cache
        root * /srv/cache/v1
        file_server
        header Access-Control-Allow-Origin *
        header Cache-Control "public, max-age=10"
    }

    handle /v1/* {
        reverse_proxy aggregator:8090
        header Access-Control-Allow-Origin *
    }

"""

target = "    handle {\n        respond"
if target not in cf:
    print("ERROR: fallback handle not found")
    sys.exit(1)

cf = cf.replace(target, v1_route + target)

with open(path, "w") as f:
    f.write(cf)
print("Added /v1/cache and /v1/* routes")
