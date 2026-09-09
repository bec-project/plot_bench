//! Open the source controls with the platform URL handler, without a shell.

pub fn command_for_url(url: &str) -> Result<(&'static str, String), String> {
    let parsed = url::Url::parse(url).map_err(|error| error.to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") || parsed.host_str().is_none() {
        return Err("Source controls require an HTTP(S) URL".into());
    }
    let command = if cfg!(target_os = "macos") {
        "/usr/bin/open"
    } else if cfg!(target_os = "linux") {
        "xdg-open"
    } else {
        return Err("Opening source controls is supported on macOS and Linux".into());
    };
    Ok((command, parsed.to_string()))
}

pub fn open(url: &str) -> Result<(), String> {
    let (command, url) = command_for_url(url)?;
    let status = std::process::Command::new(command)
        .arg(url)
        .status()
        .map_err(|error| format!("Could not open source controls with {command}: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("Source controls could not open: {status}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_non_web_handlers() {
        assert!(command_for_url("file:///etc/passwd").is_err());
        assert!(command_for_url("not a url").is_err());
    }

    #[test]
    fn url_is_one_argument_not_a_shell_command() {
        let (command, url) = command_for_url("http://localhost:8765/?value=$(test)").unwrap();
        assert_eq!(url, "http://localhost:8765/?value=$(test)");
        assert_eq!(
            command,
            if cfg!(target_os = "macos") {
                "/usr/bin/open"
            } else {
                "xdg-open"
            }
        );
    }
}
