import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import QtGraphs

ApplicationWindow {
    id: root
    readonly property int renderColumns: Math.max(1, benchmark.gridColumns)
    readonly property int renderRows: Math.max(1, Math.ceil((benchmark.waveformPlots + benchmark.imagePlots) / renderColumns))
    readonly property real dataWidth: Math.max(1, Math.floor((width - 48 - 16 * (renderColumns - 1)) / renderColumns - 120))
    readonly property real dataHeight: Math.max(1, Math.floor((height - 340 - 16 * (renderRows - 1)) / renderRows - 140))
    visible: true
    width: 1100
    height: 820
    minimumWidth: 860
    minimumHeight: 640
    color: "#0b141c"
    title: "Plotbench · Qt Graphs + custom Qt Quick image"
    font.family: "Helvetica Neue"

    component Caption: Text {
        color: "#8fa7b6"
        font.family: "Helvetica Neue"
        font.pixelSize: 11
        elide: Text.ElideRight
    }
    component Panel: Rectangle {
        color: "#111e28"
        border.color: "#253745"
        border.width: 1
        radius: 9
    }
    component PlotToggle: Button {
        required property string plot
        objectName: plot + "Toggle"
        text: plot === "waveform" ? "1D" : "2D"
        implicitWidth: 44
        implicitHeight: 23
        padding: 0
        checkable: true
        checked: benchmark.plotControls[plot + "Checked"]
        enabled: benchmark.plotControls[plot + "Enabled"]
        Accessible.name: plot === "waveform" ? "1D waveform" : "2D image"
        ToolTip.visible: hovered
        ToolTip.text: benchmark.plotControls[plot + "Tooltip"]
        onClicked: {
            benchmark.toggle_plot(plot)
            // Restore the authoritative frame state while the asynchronous request is pending.
            checked = Qt.binding(function() { return benchmark.plotControls[plot + "Checked"] })
        }
        background: Rectangle {
            color: parent.checked ? "#173239" : "#0b141c"
            border.color: parent.hovered ? "#64dccc" : parent.checked ? "#285052" : "#253745"
            radius: 4
        }
        contentItem: Text {
            text: parent.text
            color: parent.checked ? "#64dccc" : "#8fa7b6"
            font.pixelSize: 11
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        anchors.bottomMargin: 20
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 7
                Caption {
                    text: "PLOTTING BENCHMARK"
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }
                RowLayout {
                    spacing: 12
                    Text {
                        text: "Qt Graphs"
                        color: "#d8e6ed"
                        font.pixelSize: 26
                        font.weight: Font.DemiBold
                    }
                    Rectangle {
                        implicitWidth: rendererBadge.implicitWidth + 16
                        implicitHeight: 26
                        color: "#173239"
                        border.color: "#285052"
                        radius: 5
                        Caption {
                            id: rendererBadge
                            anchors.centerIn: parent
                            text: benchmark.presentation.renderer + " · " + benchmark.runMode
                            color: "#64dccc"
                            font.pixelSize: 10
                        }
                    }
                }
            }
            Item { Layout.fillWidth: true }
            ColumnLayout {
                spacing: 7
                Caption {
                    Layout.alignment: Qt.AlignRight
                    text: "● " + benchmark.presentation.state
                    color: benchmark.presentation.error ? "#ffa7a7" : "#64dccc"
                    ToolTip.visible: statusHover.hovered
                    ToolTip.text: benchmark.presentation.details
                    HoverHandler { id: statusHover }
                }
                Button {
                    text: "Source controls  ↗"
                    implicitHeight: 36
                    implicitWidth: 140
                    onClicked: benchmark.open_controls()
                    background: Rectangle {
                        color: parent.down ? "#42bbaa" : parent.hovered ? "#85e7da" : "#64dccc"
                        radius: 6
                    }
                    contentItem: Text {
                        text: parent.text
                        color: "#0b141c"
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        Panel {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                anchors.topMargin: 12
                anchors.bottomMargin: 12
                spacing: 18
                Repeater {
                    model: [
                        {heading: "TARGET RATE", value: benchmark.workload.target},
                        {heading: "WAVEFORM", value: benchmark.workload.waveform},
                        {heading: "IMAGE", value: benchmark.workload.image}
                    ]
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        spacing: 5
                        Caption { text: modelData.heading; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.value
                            color: "#d8e6ed"
                            font.pixelSize: 14
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    spacing: 3
                    Caption { text: "PLOTS"; font.pixelSize: 10; font.weight: Font.DemiBold }
                    RowLayout {
                        spacing: 6
                        PlotToggle { plot: "waveform" }
                        PlotToggle { plot: "image" }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            Repeater {
                model: [
                    {heading: "Submitted", value: benchmark.presentation.submitted, target: benchmark.metricTargets.submitted, unit: "/s"},
                    {heading: "Update time", value: benchmark.presentation.update, target: benchmark.metricTargets.update, unit: "ms"},
                    {heading: "Skipped", value: benchmark.presentation.skipped, target: benchmark.metricTargets.skipped, unit: ""},
                    {heading: "Receive age", value: benchmark.presentation.age, target: benchmark.metricTargets.age, unit: benchmark.presentation.ageUnit}
                ]
                Panel {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 88
                    ToolTip.visible: metricHover.hovered
                    ToolTip.text: benchmark.metricGuide
                    HoverHandler { id: metricHover }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        anchors.topMargin: 10
                        anchors.bottomMargin: 10
                        spacing: 3
                        Caption { text: modelData.heading }
                        RowLayout {
                            spacing: 5
                            Text {
                                text: modelData.value
                                color: "#d8e6ed"
                                font.pixelSize: 25
                                font.weight: Font.DemiBold
                            }
                            Caption { text: modelData.unit; font.pixelSize: 12; Layout.alignment: Qt.AlignBaseline }
                        }
                        Caption { text: modelData.target; font.pixelSize: 10; Layout.fillWidth: true }
                    }
                }
            }
        }

        // Shared layout rule: waveform plots first, then image plots, in a
        // ceil(sqrt(n)) column grid of equal cells; trailing cells stay empty.
        GridLayout {
            id: plotGrid
            objectName: "plotGrid"
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: benchmark.gridColumns
            columnSpacing: 16
            rowSpacing: 16

            Repeater {
                model: benchmark.waveformPlots
                Panel {
                    id: waveformPanel
                    required property int index
                    objectName: "waveformPanel-" + index
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 1
                    Text {
                        x: 16; y: 16
                        text: benchmark.waveformTitles[waveformPanel.index]
                        color: "#d8e6ed"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Caption { x: 16; y: 42; text: benchmark.workload.waveformSubtitle }
                    GraphsView {
                        id: graph
                        objectName: "waveformGraph-" + waveformPanel.index
                        x: 4
                        y: 64
                        property real axisWidth: 120
                        property real axisHeight: 80
                        width: root.dataWidth + axisWidth
                        height: root.dataHeight + axisHeight
                        // Axis labels are toolkit-sized. Solve for the actual data rectangle
                        // after layout, rather than treating GraphsView bounds as its plot area.
                        function fitDataArea() {
                            if (plotArea.width <= 0 || plotArea.height <= 0) return;
                            const dw = root.dataWidth - plotArea.width;
                            const dh = root.dataHeight - plotArea.height;
                            if (Math.abs(dw) > 0.1) axisWidth = Math.max(0, Math.min(300, axisWidth + dw));
                            if (Math.abs(dh) > 0.1) axisHeight = Math.max(0, Math.min(300, axisHeight + dh));
                        }
                        onPlotAreaChanged: Qt.callLater(fitDataArea)
                        antialiasing: false
                        axisXSmoothing: 0
                        axisYSmoothing: 0
                        gridSmoothing: 0
                        shadowVisible: false
                        theme: GraphsTheme {
                            colorScheme: GraphsTheme.ColorScheme.Dark
                            plotAreaBackgroundColor: "#111e28"
                            backgroundColor: "#111e28"
                            gridVisible: false
                            labelTextColor: "#8fa7b6"
                            labelFont.pixelSize: 11
                            labelFont.family: "Helvetica Neue"
                            axisXLabelFont.pixelSize: 11
                            axisXLabelFont.family: "Helvetica Neue"
                            axisYLabelFont.pixelSize: 11
                            axisYLabelFont.family: "Helvetica Neue"
                            axisX.mainColor: "#253745"
                            axisX.subColor: "#253745"
                            axisX.mainWidth: 1
                            axisY.mainColor: "#253745"
                            axisY.subColor: "#253745"
                            axisY.mainWidth: 1
                        }
                        axisX: ValueAxis {
                            min: 0
                            max: benchmark.xMaximum
                            tickInterval: Math.max(1, benchmark.xMaximum / 4)
                            labelDecimals: 0
                            titleText: "Sample"
                        }
                        axisY: ValueAxis {
                            min: -1.5
                            max: 1.5
                            tickInterval: 0.5
                            labelDecimals: 1
                            titleText: "Amplitude"
                        }
                    }
                    // LineSeries is not an Item, so a Repeater cannot build it and GraphsView's
                    // default seriesList property cannot hold a Repeater; an Instantiator creates
                    // one series per curve and registers it with the graph explicitly.
                    Instantiator {
                        model: benchmark.curves
                        delegate: LineSeries {
                            required property int index
                            objectName: "waveformSeries-" + waveformPanel.index + "-" + index
                            color: benchmark.curveColors[index % benchmark.curveColors.length]
                            width: 1 / root.Screen.devicePixelRatio
                        }
                        onObjectAdded: (index, object) => graph.addSeries(object)
                        onObjectRemoved: (index, object) => graph.removeSeries(object)
                    }
                }
            }

            Repeater {
                model: benchmark.imagePlots
                Panel {
                    id: imagePanel
                    required property int index
                    objectName: "imagePanel-" + index
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 1
                    Text {
                        x: 16; y: 16
                        text: benchmark.imageTitles[imagePanel.index]
                        color: "#d8e6ed"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Caption { x: 16; y: 42; text: benchmark.workload.imageSubtitle }
                    Item {
                        x: 56
                        y: 68
                        width: root.dataWidth
                        height: root.dataHeight
                        Image {
                            id: streamImage
                            objectName: "streamImage-" + imagePanel.index
                            anchors.fill: parent
                            source: imagePanel.index < benchmark.imageUrls.length
                                ? benchmark.imageUrls[imagePanel.index] : ""
                            cache: false
                            asynchronous: false
                            smooth: false
                            mipmap: false
                            fillMode: Image.PreserveAspectFit
                        }
                        Rectangle {
                            anchors.centerIn: parent
                            width: streamImage.paintedWidth
                            height: streamImage.paintedHeight
                            color: "transparent"
                            border.color: "#253745"
                            border.width: 1 / root.Screen.devicePixelRatio
                            Caption { anchors.right: parent.left; anchors.rightMargin: 9; anchors.top: parent.top; text: "0" }
                            Caption {
                                anchors.right: parent.left; anchors.rightMargin: 9; anchors.bottom: parent.bottom
                                text: benchmark.imageHeight - 1
                            }
                            Caption {
                                anchors.right: parent.left; anchors.rightMargin: 30; anchors.verticalCenter: parent.verticalCenter
                                text: "Row"; rotation: -90
                            }
                            Caption { anchors.left: parent.left; anchors.top: parent.bottom; anchors.topMargin: 6; text: "0" }
                            Caption {
                                anchors.right: parent.right; anchors.top: parent.bottom; anchors.topMargin: 6
                                text: benchmark.imageWidth - 1
                            }
                            Caption {
                                anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.bottom; anchors.topMargin: 6
                                text: "Column"
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Caption { text: "Submitted updates · not displayed FPS"; font.pixelSize: 10 }
            Item { Layout.fillWidth: true }
            Caption { text: benchmark.presentation.resources; font.pixelSize: 10 }
        }
    }
}
