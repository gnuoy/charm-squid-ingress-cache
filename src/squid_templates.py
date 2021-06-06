SQUID_TEMPLATE = """
acl localnet src 0.0.0.1-0.255.255.255	# RFC 1122 "this" network (LAN)
acl localnet src 10.0.0.0/8		# RFC 1918 local private network (LAN)
acl localnet src 100.64.0.0/10		# RFC 6598 shared address space (CGN)
acl localnet src 169.254.0.0/16 	# RFC 3927 link-local (directly plugged) machines
acl localnet src 172.16.0.0/12		# RFC 1918 local private network (LAN)
acl localnet src 192.168.0.0/16		# RFC 1918 local private network (LAN)
acl localnet src fc00::/7       	# RFC 4193 local private network range
acl localnet src fe80::/10      	# RFC 4291 link-local (directly plugged) machines
acl SSL_ports port 443
acl Safe_ports port 80		# http
acl Safe_ports port 21		# ftp
acl Safe_ports port 443		# https
acl Safe_ports port 70		# gopher
acl Safe_ports port 210		# wais
acl Safe_ports port 1025-65535	# unregistered ports
acl Safe_ports port 280		# http-mgmt
acl Safe_ports port 488		# gss-http
acl Safe_ports port 591		# filemaker
acl Safe_ports port 777		# multiling http
acl CONNECT method CONNECT
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow localhost manager
http_access deny manager
include /etc/squid/conf.d/*
http_access allow localhost
http_access allow localnet
http_access deny all
coredump_dir /var/spool/squid
{% if log_format -%}
logformat combined {{ log_format }}
{% endif -%}
{% if refresh_patterns -%}
{% for refresh_pattern in refresh_patterns -%}
{% if refresh_pattern.case_sensitive -%}
refresh_pattern -i {{ refresh_pattern.regex }} {{ refresh_pattern.min }} {{ refresh_pattern.percent }}% {{ refresh_pattern.max }} {{ refresh_pattern.options|join(' ') }}
{% else -%}
refresh_pattern {{ refresh_pattern.regex }} {{ refresh_pattern.min }} {{ refresh_pattern.percent }}% {{ refresh_pattern.max }} {{ refresh_pattern.options|join(' ') }}
{% endif -%}
{% endfor -%}
{% endif -%}
refresh_pattern . 0 20% 4320
{% if port %}
http_port {{ port }} accel
{% for peer in peers -%}
cache_peer {{ peer }} parent {{ port }} 0 no-query originserver
{% endfor -%}
{% endif %}

""" # noqa
