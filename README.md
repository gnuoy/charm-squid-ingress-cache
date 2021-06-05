# squid-ingress-cache

## Description

Charmed ingress cache using [Squid][squid-upstream] operator for Kubernetes. 

## Usage

```
juju deploy --channel=beta squid-ingress-cache
```

This charm can be added between a web service charm and a charm which
configures an ingress resource to make a workload reachable from outside
the k8s cluster. The website charm does not require any changes to
make use of the ingress cache.

```
juju deploy my-website-charm
juju deploy --channel=beta squid-ingress-cache
juju deploy nginx-ingress-integrator ingress
juju relate squid-ingress-cache:ingress-proxy my-website-charm
juju relate ingress squid-ingress-cache
```

If the website charm required more control over how caching is performed
then it can implement the `ingress-cache` interface. This interface
allows additional caching directives to be passed to the squid service.
Deployment using this interface is almost identical to the previous
example:

```
juju deploy my-website-charm
juju deploy --channel=beta squid-ingress-cache
juju deploy nginx-ingress-integrator ingress
juju relate squid-ingress-cache:ingress-cache my-website-charm
juju relate ingress squid-ingress-cache
```

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

Building docker image:

    docker image build -t squid docker
    docker image save -o squid.tar <image name>

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests

<!-- LINKS -->
[squid-upstream]: http://www.squid-cache.org/

