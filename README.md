# squid-ingress-cache

## Description

Charmed ingress cache using [Squid][squid-upstream] operator for Kubernetes. 

## Usage

This charm can be added between a web service charm and a charm which
configures an ingress resource to make a workload reachable from outside
the k8s cluster. The website charm does not require any changes to
make use of the ingress cache.

This charm can be related to another charmed application which
requires the ingress relation. This charm will then provide
a caching layer in front of the website.

    $ juju deploy website
    $ juju deploy squid-ingress-cache
    $ juju relate squid-ingress-cache:ingress-proxy website
    $ juju status
    Model  Controller          Cloud/Region        Version  SLA          Timestamp
    demo   microk8s-localhost  microk8s/localhost  2.9.2    unsupported  08:34:08Z

    App                  Version  Status  Scale  Charm                Store  Channel  Rev  OS          Address  Message
    squid-ingress-cache           active      1  squid-ingress-cache  local             0  kubernetes           
    website                       active      1  norwich              local             0  kubernetes           

    Unit                    Workload  Agent  Address       Ports  Message
    squid-ingress-cache/0*  active    idle   10.1.165.100         
    website/0*              active    idle   10.1.165.86          

The website can now be accessed either from the website unit or the
squid-ingress-cache unit

    $ curl http://10.1.165.86/index.html 2>/dev/null | md5sum -
    b1a26a427156803f49a368c7919432b2  -
    $ curl http://10.1.165.100/index.html 2>/dev/null | md5sum -
    b1a26a427156803f49a368c7919432b2  -
    $ curl -I http://10.1.165.100/index.html 2>/dev/null | grep 'X-Cache:'
    b1a26a427156803f49a368c7919432b2  -
    X-Cache: HIT from squid-ingress-cache-0

The squid-ingress-cache charm can also sit inbetween a website and
a charm which configures an ingress resource to make a workload reachable from
outside the k8s cluster. 

    $ juju deploy website
    $ juju deploy squid-ingress-cache
    $ juju deploy nginx-ingress-integrator ingress
    $ juju relate squid-ingress-cache:ingress-proxy website
    $ juju relate squid-ingress-cache:ingress ingress
    $ juju status
    Model  Controller          Cloud/Region        Version  SLA          Timestamp
    demo   microk8s-localhost  microk8s/localhost  2.9.2    unsupported  08:53:02Z

    App                  Version  Status  Scale  Charm                     Store     Channel  Rev  OS          Address  Message
    ingress                       active      1  nginx-ingress-integrator  charmhub  stable    19  kubernetes           Ingress with service IP(s): 10.152.183.56
    squid-ingress-cache           active      1  squid-ingress-cache       local                0  kubernetes           
    website                       active      1  norwich                   local                0  kubernetes           

    Unit                    Workload  Agent  Address       Ports  Message
    ingress/0*              active    idle   10.1.165.124         Ingress with service IP(s): 10.152.183.56
    squid-ingress-cache/0*  active    idle   10.1.165.116         
    website/0*              active    idle   10.1.165.102  

The website can now be accessed from the ingress resource too.

    $ curl http://10.152.183.56/index.html 2>/dev/null | md5sum -
    b1a26a427156803f49a368c7919432b2  -
    $ curl -I http://10.152.183.56/index.html 2>/dev/null | grep 'X-Cache:'
    X-Cache: HIT from squid-ingress-cache-0

## Usage

To add an additional squid-ingress-cache

    $ juju add-unit squid-ingress-cache

**NOTE** If more units are added to the website the new units will
         automatically be included in the squid config.

## Developing

Source code is currently [Here][charm-src]

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

Building squid container image for the charm to use:

    docker image build -t squid docker

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests

## Limitations

The charm does not yet support SSL.

<!-- LINKS -->
[charm-src]: https://github.com/gnuoy/charm-squid-ingress-cache
[squid-upstream]: http://www.squid-cache.org/

