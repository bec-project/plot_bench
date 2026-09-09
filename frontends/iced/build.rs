use std::{env, path::Path, process::Command};

fn command(program: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(program).args(args).output().ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn main() {
    for path in ["src", "Cargo.toml", "Cargo.lock", "build.rs"] {
        println!("cargo:rerun-if-changed={path}");
    }
    // Watch the checkout's actual HEAD and referenced branch, including worktrees.
    for name in ["HEAD", "index"] {
        if let Some(path) = command("git", &["rev-parse", "--git-path", name]) {
            println!("cargo:rerun-if-changed={path}");
        }
    }
    if let Some(branch) = command("git", &["symbolic-ref", "-q", "HEAD"])
        && let Some(path) = command("git", &["rev-parse", "--git-path", &branch])
    {
        println!("cargo:rerun-if-changed={path}");
    }
    let revision = command("git", &["rev-parse", "HEAD"]);
    let dirty = command(
        "git",
        &[
            "status",
            "--porcelain",
            "--untracked-files=normal",
            "--",
            ".",
        ],
    )
    .map(|status| (!status.is_empty()).to_string());
    let lock = Path::new("Cargo.lock")
        .exists()
        .then(|| command("git", &["hash-object", "Cargo.lock"]))
        .flatten();
    let compiler = command(
        &env::var("RUSTC").unwrap_or_else(|_| "rustc".into()),
        &["--version"],
    );
    for (key, value) in [
        ("PLOTBENCH_BUILD_REVISION", revision),
        ("PLOTBENCH_BUILD_DIRTY", dirty),
        ("PLOTBENCH_BUILD_LOCK_GIT_BLOB", lock),
        ("PLOTBENCH_BUILD_COMPILER", compiler),
    ] {
        println!(
            "cargo:rustc-env={key}={}",
            value.unwrap_or_else(|| "unavailable".into())
        );
    }
}
