# Hosted Tally

Some firms run TallyPrime on a hosted Windows server, through Remote Desktop or
RemoteApp, rather than on an office PC. Minkops supports that: each Windows user
on the server installs and connects Minkops in their own account, and Minkops
reads and writes only the Tally that user has open. This page is the checklist
for the firm and its hosting provider; [Windows app](windows-app.md) covers the
companion itself.

## How Minkops works on a shared server

- **One PC per Windows user.** The installer is per-user and needs no
  administrator rights. Each user who connects Minkops appears as their own PC
  under Connected PCs, with their own Tally port, companies and work.
- **Only the user's own Tally.** A TCP port belongs to the whole server, so the
  Tally answering on a user's port could be another user's, with another firm's
  books. Before every connection check, sync and save, the companion finds the
  Windows session that serves its port. It refuses a Tally in another session
  (`other_session`). On a remote session where it cannot tell, it refuses rather
  than assume (`ownership_unknown`).
- **A current companion.** The server sends Tally work to a PC in a remote
  session only from Minkops 0.11.0, the first release that makes this check.
- **Work runs inside the user's session.** A disconnected Remote Desktop session
  keeps Minkops running. Signing out stops it; queued work waits until the user
  signs in and Minkops reconnects.
- **Outbound only.** The companion polls Minkops over HTTPS every four seconds.
  It opens no inbound port, and its Tally port is reached only on `127.0.0.1`.

## Checklist for the hosting provider

1. **Windows.** A 64-bit Windows Server or Windows multi-session desktop that
   runs TallyPrime and Minkops (Windows 10/11 x64 compatible).
2. **A Tally port for each user.** Every user's TallyPrime must act as a server
   (Help (F1) > Settings > Connectivity: Server or Both) on a port no other user's
   Tally uses, such as 9000, 9001 and 9002. Users who share one Tally installation
   folder share its `tally.ini`, and with it one port: set the installation up so
   each user's Tally serves on its own port.
3. **The same port in Minkops.** Each user sets their PC's Tally port under
   Connected PCs. Check Tally connection then reads that port.
4. **PowerShell for users.** The check runs read-only PowerShell queries in the
   user's session: `Get-CimInstance Win32_Process` and `Get-NetTCPConnection`.
   If AppLocker, Constrained Language Mode or a similar policy blocks them, Minkops
   refuses Tally work with `ownership_unknown`.
5. **Outbound HTTPS** to `app.minkops.com` (the app and its API) and
   `minkops.com/downloads/` (companion updates).
6. **Disconnected sessions kept.** Session time limits must leave a disconnected
   session running long enough for queued work; signing users out ends it.
7. **Tally in the user's session.** Tally run as a Windows service, or one Tally
   shared by several users, is refused: Minkops reads only the Tally in the
   user's own session.
8. **Installer.** Users run `Minkops-Setup-<version>.exe` from
   `minkops.com/downloads/`. Until releases are code-signed, Windows SmartScreen
   warns on first install and the release notes say so.

## Checking a server

With two users signed in, each with Tally on their own port and Minkops
connected:

1. Each user runs **Check Tally connection** under Connected PCs. Each sees only
   their own open companies.
2. Set one user's PC to the other user's port and check again. Expect "Tally on
   port *N* belongs to another Windows user", and nothing read.
3. Restore the port. **Send diagnostics** reports the port, the Tally processes
   and each one's session.
