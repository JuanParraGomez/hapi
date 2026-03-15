from __future__ import annotations

from dataclasses import dataclass
import subprocess
import time


@dataclass
class PublicRouteConfig:
    enabled: bool
    ssh_host: str
    ssh_user: str
    ssh_key_path: str
    remote_traefik_root: str
    remote_dynamic_dir: str
    coolify_network: str


class PublicRouteService:
    def __init__(self, config: PublicRouteConfig, timeout: int = 30, poll_seconds: int = 120) -> None:
        self.config = config
        self.timeout = timeout
        self.poll_seconds = poll_seconds

    def _ssh_target(self) -> str:
        return f"{self.config.ssh_user}@{self.config.ssh_host}"

    def _ssh_base(self) -> list[str]:
        return [
            "ssh",
            "-i",
            self.config.ssh_key_path,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            self._ssh_target(),
        ]

    def _run_remote(self, script: str) -> str:
        proc = subprocess.run(
            [*self._ssh_base(), script],
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        return proc.stdout.strip()

    def bootstrap(self) -> dict[str, str]:
        if not self.config.enabled:
            return {"enabled": "false"}
        script = f"""
set -e
mkdir -p {self.config.remote_dynamic_dir}
python3 - <<'PY'
from pathlib import Path
p = Path('{self.config.remote_traefik_root}/docker-compose.yml')
s = p.read_text()
if '--providers.file.directory=/dynamic' not in s:
    s = s.replace('--providers.docker.exposedbydefault=false', '--providers.docker.exposedbydefault=false\\n      - "--providers.file.directory=/dynamic"\\n      - "--providers.file.watch=true"')
if './dynamic:/dynamic' not in s:
    s = s.replace('./acme.json:/acme.json', './acme.json:/acme.json\\n      - "./dynamic:/dynamic"')
if '\\n      - coolify' not in s:
    s = s.replace('    networks:\\n      - proxy', '    networks:\\n      - proxy\\n      - coolify')
if '  coolify:\\n    external: true' not in s:
    s = s + '\\n  coolify:\\n    external: true\\n'
p.write_text(s)
PY
docker network connect {self.config.coolify_network} traefik >/dev/null 2>&1 || true
cd {self.config.remote_traefik_root} && docker compose up -d >/dev/null
"""
        self._run_remote(script)
        return {"enabled": "true", "dynamic_dir": self.config.remote_dynamic_dir}

    def list_candidate_containers(self, application_uuid: str) -> list[str]:
        if not self.config.enabled:
            return []
        script = f"""python3 - <<'PY'
import subprocess

prefix = "{application_uuid}-"

def collect(args):
    proc = subprocess.run(args, capture_output=True, text=True, check=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip().startswith(prefix)]

def sort_key(name: str) -> int:
    try:
        return int(name.rsplit("-", 1)[1])
    except Exception:
        return -1

running = collect(["docker", "ps", "--format", "{{{{.Names}}}}"])
all_names = collect(["docker", "ps", "-a", "--format", "{{{{.Names}}}}"])
selected = sorted(running, key=sort_key, reverse=True) + [
    name for name in sorted(all_names, key=sort_key, reverse=True) if name not in running
]
print("\\n".join(selected))
PY"""
        try:
            result = self._run_remote(script)
        except subprocess.CalledProcessError:
            return []
        return [line.strip() for line in result.splitlines() if line.strip()]

    def resolve_container_ip(self, container_name: str) -> str | None:
        if not self.config.enabled:
            return None
        script = (
            "docker inspect "
            f"{container_name} "
            f"--format '{{{{with index .NetworkSettings.Networks \"{self.config.coolify_network}\"}}}}{{{{.IPAddress}}}}{{{{end}}}}'"
        )
        try:
            ip_address = self._run_remote(script)
        except subprocess.CalledProcessError:
            return None
        return ip_address or None

    def wait_for_container_ip(self, application_uuid: str) -> tuple[str | None, str | None]:
        deadline = time.time() + self.poll_seconds
        last_candidate = None
        while time.time() < deadline:
            for candidate in self.list_candidate_containers(application_uuid):
                last_candidate = candidate
                candidate_ip = self.resolve_container_ip(candidate)
                if candidate_ip:
                    return candidate, candidate_ip
            time.sleep(2)
        return last_candidate, None

    def publish_route(self, slug: str, domain: str, application_uuid: str, port: int) -> dict[str, str]:
        if not self.config.enabled:
            return {"enabled": "false"}
        self.bootstrap()
        container_name, container_ip = self.wait_for_container_ip(application_uuid)
        if not container_name:
            raise ValueError(f"coolify_container_not_found:{application_uuid}")
        if not container_ip:
            raise ValueError(f"coolify_container_ip_not_found:{container_name}")
        route_name = slug.replace(".", "-")
        yaml = f"""http:
  routers:
    {route_name}-web:
      entryPoints:
        - web
      rule: Host(`{domain}`)
      middlewares:
        - {route_name}-redirect
      service: {route_name}-svc
    {route_name}-websecure:
      entryPoints:
        - websecure
      rule: Host(`{domain}`)
      middlewares:
        - {route_name}-gzip
      tls: {{}}
      service: {route_name}-svc
  middlewares:
    {route_name}-redirect:
      redirectScheme:
        scheme: https
    {route_name}-gzip:
      compress: {{}}
  services:
    {route_name}-svc:
      loadBalancer:
        servers:
          - url: http://{container_ip}:{port}
"""
        script = f"""cat > {self.config.remote_dynamic_dir}/{route_name}.yaml <<'EOF'
{yaml}
EOF
sleep 2
"""
        self._run_remote(script)
        return {
            "container_name": container_name,
            "container_ip": container_ip,
            "domain": domain,
            "dynamic_file": f"{self.config.remote_dynamic_dir}/{route_name}.yaml",
        }
