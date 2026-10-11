import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root
  property var shell: null
  property var manifest: null
  property bool opened: false
  property var tabs: []
  property var results: []
  property string error: ""
  property bool slotVisible: false
  property int selected: 0
  readonly property var preview: results.length > 0 && selected >= 0 ? results[selected] : null
  readonly property bool hasSummoned: tabs.some(function(tab) { return tab.workspace === "special:chrome-search" })

  function open(_) {
    opened = true
    search.text = ""
    selected = 0
    refresh()
    Qt.callLater(function() { search.forceActiveFocus() })
  }
  function close() { opened = false }
  function showSlot() { slotVisible = true; return "ok" }
  function hideSlot() { slotVisible = false; return "ok" }
  function dismiss() {
    opened = false
    if (shell) shell.hide("hjanuschka.chrome-search")
  }
  function refresh() {
    if (!listing.running) {
      listing.command = ["omarchy-chrome-search", "list"]
      listing.running = true
    }
  }
  function workspaceLabel(workspace) {
    if (!workspace) return "?"
    if (workspace.indexOf("special:") === 0) return "S"
    return workspace.toUpperCase()
  }
  function domain(url) {
    var match = String(url || "").match(/^[a-z]+:\/\/([^/]+)/i)
    return match ? match[1] : url
  }
  function score(tab, terms) {
    var title = tab.title.toLowerCase()
    var url = tab.url.toLowerCase()
    var points = 0
    for (var i = 0; i < terms.length; i++) {
      var word = terms[i]
      if (title.indexOf(word) === 0) points += 100
      else if (title.indexOf(word) !== -1) points += 60
      else if (url.indexOf(word) !== -1) points += 15
      else return -1
    }
    return points
  }
  function filter(resetSelection) {
    var query = search.text.toLowerCase().trim()
    var terms = query ? query.split(/\s+/) : []
    var previous = !resetSelection && results[selected] ? results[selected].id : -1
    var matches = tabs.filter(function(tab) { return root.score(tab, terms) >= 0 })
    matches.sort(function(a, b) {
      return root.score(b, terms) - root.score(a, terms) || b.lastAccessed - a.lastAccessed
    })
    results = matches.slice(0, 50)
    selected = Math.max(0, results.findIndex(function(tab) { return tab.id === previous }))
  }
  function activate(centered) {
    if (error) return
    if (centered && hasSummoned) {
      Quickshell.execDetached(["omarchy-chrome-search", "restore"])
      dismiss()
      return
    }
    if (results.length > 0) {
      Quickshell.execDetached(["omarchy-chrome-search", centered ? "summon" : "activate", String(results[selected].id)])
    } else if (search.text.trim()) {
      Quickshell.execDetached(["omarchy-chrome-search", "search", search.text.trim()])
    } else {
      return
    }
    dismiss()
  }

  Process {
    id: listing
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          root.tabs = JSON.parse(text)
          root.error = ""
          root.filter(false)
        } catch (e) { root.error = "Chromium bridge unavailable" }
      }
    }
    onExited: exitCode => { if (exitCode !== 0) root.error = "Chromium bridge unavailable" }
  }
  FloatingWindow {
    visible: root.slotVisible
    title: "Omarchy Chrome Search Slot"
    color: Color.menu.background
    implicitWidth: 600
    implicitHeight: 400
    Text {
      anchors.centerIn: parent
      text: "Chrome window peeked"
      color: Color.menu.text
    }
  }
  Timer {
    interval: 2000
    repeat: true
    running: root.opened
    onTriggered: root.refresh()
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-chrome-search"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle { anchors.fill: parent; color: Color.menu.scrim }
    MouseArea { anchors.fill: parent; onClicked: root.dismiss() }

    BorderSurface {
      id: card
      width: Math.min(Style.space(640), panel.width - Style.gapsOut * 2)
      height: Math.min(Style.space(630), panel.height - Style.gapsOut * 2)
      anchors.centerIn: parent
      radius: Style.cornerRadius
      color: Color.menu.background
      borderSpec: Border.surfaceSpec("menu", "border", Color.menu.border, 1)
      padding: Style.spacing.panelPadding
      MouseArea { anchors.fill: parent; onClicked: {} }

      Column {
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.spacing.md

        TextInput {
          id: search
          width: parent.width
          height: Style.space(40)
          color: Color.menu.text
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.heading
          clip: true
          Text {
            visible: !search.text
            text: "Search Chromium tabs or type a query"
            color: Color.menu.text
            opacity: 0.5
            font: search.font
          }
          onTextChanged: root.filter(true)
          Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape) {
              root.dismiss()
              event.accepted = true
            } else if (event.key === Qt.Key_Down) {
              root.selected = Math.min(root.selected + 1, Math.max(0, root.results.length - 1))
              if (root.results.length) resultList.positionViewAtIndex(root.selected, ListView.Contain)
              event.accepted = true
            } else if (event.key === Qt.Key_Up) {
              root.selected = Math.max(0, root.selected - 1)
              if (root.results.length) resultList.positionViewAtIndex(root.selected, ListView.Contain)
              event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
              root.activate(!!(event.modifiers & Qt.ControlModifier))
              event.accepted = true
            }
          }
        }
        Text {
          textFormat: Text.PlainText
          text: root.error || (root.hasSummoned ? "Peek active | Super+Shift+C puts Chrome back" :
            (search.text ? root.results.length + " matches across " + root.tabs.length + " tabs" : root.tabs.length + " open tabs"))
          color: Color.menu.text
          opacity: 0.65
        }
        Rectangle {
          width: parent.width
          height: Style.space(40)
          visible: root.hasSummoned
          radius: Style.cornerRadius
          color: Color.menu.selectedBackground
          Text {
            anchors.centerIn: parent
            text: "End peek and restore the original tile  [Super+Shift+C]"
            color: Color.menu.selectedText
            font.family: Style.font.menuFamily
          }
          MouseArea { anchors.fill: parent; onClicked: root.activate(true) }
        }
        ListView {
          id: resultList
          width: parent.width
          height: Math.max(Style.space(100), parent.height - search.height - Style.space(root.hasSummoned ? 280 : 230))
          clip: true
          model: root.results
          Text {
            anchors.centerIn: parent
            visible: resultList.count === 0 && !root.error
            text: search.text ? "No tabs found. Press Enter to search the web." : "No open Chrome tabs"
            color: Color.menu.text
            opacity: 0.7
          }
          delegate: Rectangle {
            required property int index
            required property var modelData
            width: resultList.width
            height: Style.space(58)
            radius: Style.cornerRadius
            color: index === root.selected ? Color.menu.selectedBackground : "transparent"
            Row {
              anchors.fill: parent
              anchors.margins: Style.space(6)
              spacing: Style.spacing.md
              Rectangle {
                width: Style.space(44)
                height: Style.space(42)
                radius: Style.cornerRadius
                color: index === root.selected ? Color.menu.background : Color.menu.selectedBackground
                Text {
                  anchors.centerIn: parent
                  text: root.workspaceLabel(modelData.workspace)
                  color: Color.menu.text
                  font.family: Style.font.menuFamily
                }
              }
              Column {
                width: parent.width - Style.space(44) - parent.spacing
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: modelData.title || modelData.url
                  color: index === root.selected ? Color.menu.selectedText : Color.menu.text
                  font.family: Style.font.menuFamily
                  elide: Text.ElideRight
                }
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: root.domain(modelData.url)
                  color: Color.menu.text
                  opacity: 0.6
                  elide: Text.ElideRight
                }
              }
            }
            MouseArea {
              anchors.fill: parent
              onClicked: { root.selected = index; root.activate(false) }
            }
          }
        }
        Rectangle {
          width: parent.width
          height: Style.space(130)
          radius: Style.cornerRadius
          color: Color.menu.selectedBackground
          visible: !!root.preview

          Column {
            anchors.fill: parent
            anchors.margins: Style.spacing.md
            spacing: Style.spacing.xs
            Text {
              width: parent.width
              textFormat: Text.PlainText
              text: root.preview ? root.preview.title : ""
              color: Color.menu.selectedText
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.heading
              elide: Text.ElideRight
            }
            Text {
              width: parent.width
              textFormat: Text.PlainText
              text: root.preview ? root.preview.url : ""
              color: Color.menu.selectedText
              wrapMode: Text.WrapAnywhere
              maximumLineCount: 2
              elide: Text.ElideRight
            }
            Text {
              text: root.preview ? "WORKSPACE " + (root.preview.workspace || "?") +
                    (root.preview.active ? " | ACTIVE TAB" : "") + " | " + root.domain(root.preview.url) : ""
              color: Color.menu.selectedText
              opacity: 0.7
            }
          }
        }
        Text {
          text: root.hasSummoned ? "Super+Shift+C: end peek and return" :
            (root.results.length > 0 ? "Enter: focus tab    Ctrl+Enter: peek (center Chrome)" :
              "Enter: search with Chromium's default engine")
          color: Color.menu.text
          opacity: 0.7
        }
      }
    }
  }
}
