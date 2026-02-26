# Tailscale SSH for Devcontainers

Implementation log for adding Tailscale direct SSH access to the vigOS devcontainer.
Prototyped in `fd5`, intended for upstream integration into `vig-os/devcontainer`.

## Problem

Cursor GUI connected to a devcontainer via the devcontainer protocol cannot execute
shell commands through the AI agent. The agent's shell tool fails to route commands
into the container's remote execution context. This is a Cursor IDE limitation, not
a container or project issue.

VS Code's devcontainer protocol works fine. Cursor's CLI/terminal mode also works.
Only Cursor GUI + devcontainer protocol is broken.

## Solution

Run Tailscale inside the devcontainer with SSH enabled. Connect Cursor via
SSH remote (`ssh root@<hostname>`) instead of the devcontainer protocol.
No jump hosts, no port forwarding — direct mesh access over the tailnet.

## Architecture decisions

| Decision | Choice | Rationale |
|---|---|---|
| Networking mode | `--tun=userspace-networking` | No `/dev/net/tun` device needed. Tailscale SSH is handled by the daemon directly, not through the TUN interface. Works in any container runtime without extra device mounts. |
| SSH server | Tailscale SSH (`--ssh`) | No need to install/configure openssh-server. Auth is handled by Tailscale ACLs. |
| Auth mechanism | `TAILSCALE_AUTHKEY` env var | Passed via `docker-compose.local.yaml` (git-ignored). Recommended: reusable + ephemeral keys so stale containers auto-expire. |
| Opt-in strategy | No-op when `TAILSCALE_AUTHKEY` is unset | Install is skipped in post-create, start is skipped in post-start. Zero impact on users who don't set the key. |
| Install method | `curl -fsSL https://tailscale.com/install.sh \| sh` | Official installer, idempotent. Runs once in post-create. |
| State persistence | `/var/lib/tailscale/tailscaled.state` | Inside the container volume. Lost on container recreate, which is fine with ephemeral auth keys (re-registers automatically). |
| Hostname | `TAILSCALE_HOSTNAME` env var, default `<project>-devc-<server>` | Disambiguates same repo on different machines. Derived from `hostname -s`. Override via env var. |

## Files changed (relative to `.devcontainer/`)

### New: `scripts/setup-tailscale.sh`

Single script with two subcommands:

- `install` — installs Tailscale if `TAILSCALE_AUTHKEY` is set and Tailscale isn't
  already present. Called from `post-create.sh`.
- `start` — starts `tailscaled` daemon (userspace networking) and runs `tailscale up`
  with `--ssh` and `--authkey`. Called from `post-start.sh`.

### Modified: `scripts/post-create.sh`

Added one line at the end (before the "complete" echo):

```bash
"$SCRIPT_DIR/setup-tailscale.sh" install
```

### Modified: `scripts/post-start.sh`

Added `SCRIPT_DIR` resolution and one call at the end (before the "complete" echo):

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/setup-tailscale.sh" start
```

### Modified: `docker-compose.local.yaml`

Added commented example showing how to set `TAILSCALE_AUTHKEY` and `TAILSCALE_HOSTNAME`.
This file is git-ignored — each developer configures their own.

### Modified: `README.md`

Added "Tailscale SSH" section with setup instructions, covering:
key generation, env var configuration, rebuild, and SSH connection.

## User setup (end-to-end)

### 1. Configure Tailscale SSH ACLs

Before the container can accept SSH connections, your tailnet's ACL policy
must allow SSH access. In the Tailscale admin console
(https://login.tailscale.com/admin/acls/file), add an SSH rule:

```jsonc
"ssh": [
  {
    "action": "accept",
    "src":    ["autogroup:member"],
    "dst":    ["autogroup:self"],
    "users":  ["root", "autogroup:nonroot"]
  }
]
```

Adjust `src` and `dst` to match your tailnet's security model. Without this
rule, `tailscale ssh` connections will be rejected even though the node is
visible on the tailnet.

### 2. Generate a Tailscale auth key

Generate an auth key at https://login.tailscale.com/admin/settings/keys
(Reusable + Ephemeral recommended).

### 3. Configure the devcontainer

Edit `.devcontainer/docker-compose.local.yaml`:

```yaml
services:
  devcontainer:
    environment:
      - TAILSCALE_AUTHKEY=tskey-auth-XXXX
      - TAILSCALE_HOSTNAME=fd5-devc-mybox  # optional, default: fd5-devc-<server hostname>
```

### 4. Rebuild and let Tailscale install

Rebuild the devcontainer (or recreate if it doesn't exist yet).

Post-create installs Tailscale inside the container via the official
installer (`curl -fsSL https://tailscale.com/install.sh | sh`). This adds
~10s to the first build. Post-start then connects to the tailnet.

If the automatic install fails (e.g. network issues during build), you can
install manually inside the container:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
/path/to/.devcontainer/scripts/setup-tailscale.sh start
```

The container's Tailscale IP is printed in the post-start output.

### 5. Connect via SSH

From any machine on the tailnet:

```
ssh root@fd5-devc-mybox
```

### 6. Connect Cursor via SSH remote

In Cursor, use "Remote - SSH" to connect to `root@<hostname>`.

On first connection, Cursor installs its remote server inside the container.
The server requires authentication via a **Cursor token**. If prompted
(or if agent/extension features don't work), run the following inside the
container to authenticate:

```bash
cursor tunnel --accept-server-license-terms --name <hostname>
```

Alternatively, Cursor may display a URL + code in the IDE for browser-based
authentication. Follow the prompt to complete the device auth flow.

Once authenticated, the agent shell and all extensions work normally over
the SSH remote.

## Known gap: Git commit signing over Tailscale SSH

When connecting to the devcontainer via Tailscale SSH (instead of the
devcontainer protocol), **git commit signing does not work out of the box**.

The devcontainer image sets `user.signingkey` to an SSH public key
(`/root/.ssh/id_ed25519_github.pub`), but two things are missing:

1. **The private key is not present.** Only the `.pub` file exists inside the
   container. The private key lives on the host and is normally forwarded via
   SSH agent forwarding — but Tailscale SSH doesn't forward the host's SSH
   agent into the container session.

2. **Git signing config is incomplete.** The following settings are not set:

   ```gitconfig
   [commit]
       gpgsign = true
   [gpg]
       format = ssh
   [gpg "ssh"]
       allowedSignersFile = <path>   # needed for verification only
   ```

### Workarounds

- **Forward the SSH agent manually.** If you SSH into the Tailscale container
  from a host that has the private key, use `ssh -A root@<hostname>` so the
  agent is available inside the session. Then set the missing git config:

  ```bash
  git config --global commit.gpgsign true
  git config --global gpg.format ssh
  ```

- **Copy the private key into the container.** Mount or copy the signing key
  into the container (e.g. via `docker-compose.local.yaml` volume mount) and
  set the config. This is less secure since the key is at rest inside the
  container.

- **Use a different signing key.** Generate a container-local signing key,
  register it with GitHub, and configure git to use it.

### Upstream fix

The `post-start.sh` or `setup-tailscale.sh` script should detect whether
an SSH agent is available and, if not, print a warning that commit signing
will not work. The git signing config (`commit.gpgsign`, `gpg.format`)
should be set alongside `user.signingkey` in the devcontainer image or
init script so that signing works automatically when the key is available.

## Upstream considerations for `vig-os/devcontainer`

- The `TAILSCALE_HOSTNAME` default should be templated to `<project>-devc-<server>`
  (project name from `init-workspace.sh`, server from `hostname -s` at runtime).
- `setup-tailscale.sh` can ship as part of the standard scripts directory.
  The opt-in design means it's zero-cost for users who don't set the key.
- The `docker-compose.local.yaml` example block should be included in the
  template that `init-workspace.sh` generates.
- Consider whether to bake Tailscale into the container image to avoid the
  ~10s install-on-first-create latency. Trade-off: image size vs. cold-start time.
- Tailscale ACL policy should be documented — users need to allow SSH access
  to tagged devices or specific users in their tailnet admin console.
