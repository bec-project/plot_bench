// Plotbench Qt Graphs C++ frontend: native Qt Graphs LineSeries plus a custom Qt Quick image.
#include <QCommandLineParser>
#include <QDir>
#include <QEventLoop>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLibraryInfo>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QTimer>
#include <cstdio>
#include <cstring>

#include "controller.h"
#include "image_provider.h"

using namespace plotbench;

namespace {

bool fetchColorTable(const QString &url, FrameImageProvider *provider, QString *error) {
    QNetworkAccessManager network;
    for (int attempt = 0; attempt < 20; ++attempt) {
        QNetworkReply *reply = network.get(QNetworkRequest(QUrl(url + QStringLiteral("/api/colormap"))));
        QEventLoop loop;
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        QTimer::singleShot(3000, &loop, &QEventLoop::quit);
        loop.exec();
        const bool ok = reply->isFinished() && reply->error() == QNetworkReply::NoError;
        const QByteArray body = ok ? reply->readAll() : QByteArray();
        *error = reply->errorString();
        reply->abort();
        reply->deleteLater();
        if (ok) {
            const QJsonArray table = QJsonDocument::fromJson(body).array();
            QList<QRgb> colors;
            for (const QJsonValue &entry : table) {
                const QJsonArray rgb = entry.toArray();
                if (rgb.size() != 3) {
                    break;
                }
                colors.append(qRgb(rgb.at(0).toInt(), rgb.at(1).toInt(), rgb.at(2).toInt()));
            }
            if (colors.size() == 256) {
                provider->setColorTable(colors);
                return true;
            }
            *error = QStringLiteral("colormap must contain 256 RGB entries");
            return false;
        }
        QEventLoop wait;
        QTimer::singleShot(500, &wait, &QEventLoop::quit);
        wait.exec();
    }
    return false;
}

}  // namespace

int main(int argc, char *argv[]) {
    if (argc == 2 && std::strcmp(argv[1], "--runtime-info") == 0) {
        QCoreApplication app(argc, argv);
        const QDir platforms(QLibraryInfo::path(QLibraryInfo::PluginsPath) + QStringLiteral("/platforms"));
        QJsonArray plugins;
        for (const QString &name : platforms.entryList({QStringLiteral("*qwayland*.so")}, QDir::Files)) {
            plugins.append(platforms.absoluteFilePath(name));
        }
        const QByteArray output = QJsonDocument(QJsonObject{
            {QStringLiteral("qt"), QString::fromLatin1(qVersion())},
            {QStringLiteral("wayland_plugins"), plugins},
        }).toJson(QJsonDocument::Compact);
        std::puts(output.constData());
        return 0;
    }
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Plotbench Qt Graphs C++"));
    app.setApplicationVersion(QStringLiteral(PLOTBENCH_APP_VERSION));

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Shared-source plotting benchmark: Qt Graphs (C++) and a custom Qt Quick image"));
    parser.addHelpOption();
    parser.addVersionOption();
    parser.addOption({QStringLiteral("url"), QStringLiteral("Source base URL"), QStringLiteral("url"), QStringLiteral("http://127.0.0.1:8765")});
    parser.addOption({QStringLiteral("mode"), QStringLiteral("stream|replay"), QStringLiteral("mode"), QStringLiteral("stream")});
    parser.addOption({QStringLiteral("run-id"), QStringLiteral("Run identifier for telemetry"), QStringLiteral("id"), QStringLiteral("demo")});
    parser.addOption({QStringLiteral("duration"), QStringLiteral("Seconds after the first submission; 0 runs until closed"), QStringLiteral("seconds"), QStringLiteral("0")});
    parser.addOption({QStringLiteral("width"), QStringLiteral("Logical window width"), QStringLiteral("pixels"), QStringLiteral("1100")});
    parser.addOption({QStringLiteral("height"), QStringLiteral("Logical window height"), QStringLiteral("pixels"), QStringLiteral("820")});
    parser.process(app);

    Options options;
    options.url = parser.value(QStringLiteral("url"));
    options.mode = parser.value(QStringLiteral("mode"));
    options.runId = parser.value(QStringLiteral("run-id"));
    bool ok = false;
    options.duration = parser.value(QStringLiteral("duration")).toDouble(&ok);
    if (!ok || options.duration < 0 || !std::isfinite(options.duration)) {
        std::fputs("duration must be finite and nonnegative\n", stderr);
        return 2;
    }
    options.width = parser.value(QStringLiteral("width")).toInt(&ok);
    if (!ok || options.width <= 0) {
        std::fputs("width must be positive\n", stderr);
        return 2;
    }
    options.height = parser.value(QStringLiteral("height")).toInt(&ok);
    if (!ok || options.height <= 0) {
        std::fputs("height must be positive\n", stderr);
        return 2;
    }
    if (options.mode != QLatin1String("stream") && options.mode != QLatin1String("replay")) {
        std::fputs("mode must be stream or replay\n", stderr);
        return 2;
    }
    if (!options.url.startsWith(QLatin1String("http://")) && !options.url.startsWith(QLatin1String("https://"))) {
        std::fputs("source URL must use http or https\n", stderr);
        return 2;
    }
    while (options.url.endsWith(QLatin1Char('/'))) {
        options.url.chop(1);
    }

    QQuickStyle::setStyle(QStringLiteral("Basic"));
    auto *provider = new FrameImageProvider();  // the engine takes ownership below
    QString colormapError;
    if (!fetchColorTable(options.url, provider, &colormapError)) {
        std::fprintf(stderr, "Could not fetch the shared colormap from %s: %s\n", qPrintable(options.url), qPrintable(colormapError));
        delete provider;
        return 1;
    }
    // The controller is declared before the engine so QML bindings never observe a
    // destroyed context object while the engine tears down.
    Controller controller(options, provider);
    QQmlApplicationEngine engine;
    engine.addImageProvider(QStringLiteral("frames"), provider);
    engine.rootContext()->setContextProperty(QStringLiteral("benchmark"), &controller);
    engine.setInitialProperties({{QStringLiteral("width"), options.width}, {QStringLiteral("height"), options.height}});
    engine.loadFromModule(QStringLiteral("PlotbenchQtGraphsCpp"), QStringLiteral("Main"));
    if (engine.rootObjects().isEmpty()) {
        controller.close();
        std::fputs("Failed to load the Qt Graphs QML window\n", stderr);
        return 1;
    }
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    if (!window) {
        controller.close();
        std::fputs("The QML root object is not a window\n", stderr);
        return 1;
    }
    QObject::connect(&app, &QGuiApplication::aboutToQuit, &controller, &Controller::close);
    if (!controller.start(window)) {
        controller.close();
        std::fprintf(stderr, "%s\n", qPrintable(controller.failure()));
        return 1;
    }
    const int result = app.exec();
    const QString failure = controller.failure();
    if (!failure.isEmpty() || controller.submitted() == 0) {
        std::fprintf(stderr, "%s\n", failure.isEmpty() ? "No frames submitted" : qPrintable(failure));
        return 1;
    }
    return result;
}
