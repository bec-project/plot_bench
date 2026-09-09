use anyhow::{Context, Result};
use axum::serve::ListenerExt;
use clap::Parser;
use plotbench_source_rust::{
    config::Config,
    server::{RunningSource, app},
};
use std::{future::IntoFuture, path::PathBuf, time::Duration};

#[derive(Parser)]
#[command(
    version,
    about = "Native Rust source for the shared plotting benchmark protocol"
)]
struct Args {
    #[arg(long, default_value = "127.0.0.1")]
    host: String,
    #[arg(long, default_value_t = 8765)]
    port: u16,
    /// JSON configuration file; omitted fields use protocol defaults.
    #[arg(long)]
    config: PathBuf,
    #[arg(long)]
    output: PathBuf,
    /// Shared controls.html supplied by the monorepo launcher.
    #[arg(long)]
    controls: PathBuf,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    let config: Config =
        serde_json::from_slice(&std::fs::read(&args.config).context("Cannot read config file")?)?;
    config.validate()?;
    let controls = std::fs::read_to_string(args.controls).context("Cannot read controls HTML")?;
    let mut source = RunningSource::start(config, args.output, controls)?;
    let listener = tokio::net::TcpListener::bind((args.host.as_str(), args.port)).await?;
    eprintln!("Rust source listening on http://{}", listener.local_addr()?);
    let listener = listener.tap_io(|stream| {
        if let Err(error) = stream.set_nodelay(true) {
            eprintln!("Cannot enable TCP_NODELAY: {error}");
        }
    });
    let state = source.state.clone();
    let shutdown_state = state.clone();
    let mut stopping = state.shutdown_receiver();
    let serving = axum::serve(listener, app(state))
        .with_graceful_shutdown(async move {
            #[cfg(unix)]
            {
                let mut terminate =
                    tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                        .expect("SIGTERM handler");
                tokio::select! { _=tokio::signal::ctrl_c()=>{}, _=terminate.recv()=>{} }
            }
            #[cfg(not(unix))]
            let _ = tokio::signal::ctrl_c().await;
            shutdown_state.request_shutdown();
        })
        .into_future();
    tokio::pin!(serving);
    tokio::select! {
        result = &mut serving => result?,
        _ = stopping.wait_for(|stopped| *stopped) => {
            match tokio::time::timeout(Duration::from_secs(3), &mut serving).await {
                Ok(result) => result?,
                Err(_) => eprintln!("HTTP shutdown drain reached 3 seconds; closing stalled connections"),
            }
        }
    }
    source.stop();
    Ok(())
}
