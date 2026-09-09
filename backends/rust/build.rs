fn main() {
    let rustc = std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into());
    let output = std::process::Command::new(rustc)
        .arg("--version")
        .output()
        .expect("rustc version");
    let version = String::from_utf8(output.stdout).expect("UTF-8 rustc version");
    println!("cargo:rustc-env=PLOTBENCH_RUSTC_VERSION={}", version.trim());
}
