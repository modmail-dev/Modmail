# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

# v2.0.0

This release introduces the use of our centralized [API service](https://github.com/kyb3r/webserver) to enable dynamic configuration, auto-updates, and thread logs. To use this release you must acquire an API token from https://dashboard.modmail.tk. Read the installation guide [here](https://github.com/kyb3r/modmail/wiki/installation).

### Changed
- Stability improvements through synchronization primitives 
- Refactor thread management and code
- Update command now uses `api.modmail.tk`
- Removed `archive` command

### Fixed
- Status command now changes playing status indefinitely

### Added
- Dynamic help command
- Dynamic configuration through `api.modmail.tk`
- Thread logs via `logs.modmail.tk`
- Automatic updates
- Dynamic command aliases and snippets
- Optional support for using a seperate guild as the operations center