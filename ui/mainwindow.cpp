#include "mainwindow.h"
#include "./ui_mainwindow.h"

#include <QAbstractButton>
#include <QButtonGroup>
#include <QComboBox>
#include <QDebug>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QKeySequence>
#include <QLabel>
#include <QLineEdit>
#include <QMenuBar>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QScrollArea>
#include <QShortcut>
#include <QSignalBlocker>
#include <QStackedWidget>
#include <QStatusBar>
#include <QTextCursor>
#include <QTime>
#include <QTimer>
#include <QVBoxLayout>
#include <memory>
#include <vector>

namespace {

// ---- Change this to your own app name -----------------------------------
const char *const kAppName = "Campus Guide";
// -------------------------------------------------------------------------

// Painted icons for the header tabs and search box
class LineIcon : public QWidget
{
public:
    enum Kind { Search, Pin, Mail, List };

    explicit LineIcon(Kind kind, const QColor &color = Qt::white, QWidget *parent = nullptr)
        : QWidget(parent), m_kind(kind), m_color(color)
    {
        setFixedSize(28, 28);
    }

    void setColor(const QColor &c) { m_color = c; update(); }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        p.setPen(QPen(m_color, 2.4, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
        p.setBrush(Qt::NoBrush);

        switch (m_kind) {
        case Search:
            p.drawEllipse(QPointF(12, 12), 7.5, 7.5);
            p.drawLine(QPointF(17.5, 17.5), QPointF(25, 25));
            break;
        case Pin:
            p.drawEllipse(QPointF(14, 11), 7.5, 7.5);
            p.drawLine(QPointF(8.2, 16.2), QPointF(14, 25));
            p.drawLine(QPointF(19.8, 16.2), QPointF(14, 25));
            p.setBrush(m_color);
            p.drawEllipse(QPointF(14, 11), 2.4, 2.4);
            break;
        case Mail: {
            p.drawRoundedRect(QRectF(3, 7, 22, 15), 3, 3);
            QPolygonF flap;
            flap << QPointF(4, 9) << QPointF(14, 16) << QPointF(24, 9);
            p.drawPolyline(flap);
            break;
        }
        case List:
            for (int k = 0; k < 3; ++k) {
                const qreal y = 8 + k * 6.5;
                p.drawLine(QPointF(10, y), QPointF(25, y));
                p.drawPoint(QPointF(4.5, y));
            }
            break;
        }
    }

private:
    Kind m_kind;
    QColor m_color;
};

// Toggle switch used in the filter pills
class ToggleSwitch : public QAbstractButton
{
public:
    explicit ToggleSwitch(const QColor &onColor, QWidget *parent = nullptr)
        : QAbstractButton(parent), m_on(onColor)
    {
        setCheckable(true);
        setCursor(Qt::PointingHandCursor);
        setFixedSize(40, 22);
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        p.setPen(Qt::NoPen);
        p.setBrush(isChecked() ? m_on : QColor("#b8c6c2"));
        p.drawRoundedRect(rect(), height() / 2.0, height() / 2.0);
        const int d = height() - 6;
        const int x = isChecked() ? width() - d - 3 : 3;
        p.setBrush(Qt::white);
        p.drawEllipse(QRectF(x, 3, d, d));
    }

private:
    QColor m_on;
};

// Place photo (rounded). Shows a placeholder if the file is missing.
class ImageBox : public QWidget
{
public:
    explicit ImageBox(const QString &path, QWidget *parent = nullptr)
        : QWidget(parent)
    {
        if (!path.isEmpty())
            m_pix.load(path);
        setFixedWidth(140);
        setMinimumHeight(130);
        setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        QPainterPath clip;
        clip.addRoundedRect(QRectF(rect()), 14, 14);
        p.setClipPath(clip);

        if (!m_pix.isNull()) {
            const QPixmap s = m_pix.scaled(size(), Qt::KeepAspectRatioByExpanding,
                                           Qt::SmoothTransformation);
            p.drawPixmap((width() - s.width()) / 2, (height() - s.height()) / 2, s);
        } else {
            QLinearGradient g(0, 0, 0, height());
            g.setColorAt(0, QColor("#e3f3f0"));
            g.setColorAt(1, QColor("#bfdcd6"));
            p.fillRect(rect(), g);
            p.setPen(QColor("#7aa39b"));
            p.drawText(rect(), Qt::AlignCenter, "PHOTO");
        }
    }

private:
    QPixmap m_pix;
};

// ---- Data ---------------------------------------------------------------
struct Place {
    const char *name;
    const char *building;
    const char *floor;
    const char *desc;
    int openHour;          // 24h clock, e.g. 9
    int closeHour;         // e.g. 17
    bool accessible;       // lift / ramp available
    const char *image;     // file path or :/resource path (optional)
};

struct PlaceCategory {
    const char *name;
    const char *shortText; // shown until you add an image
    const char *image;
    std::vector<Place> items;
};

struct Person {
    const char *name;
    const char *role;
    const char *location;  // must match a Place name
};

struct Page {
    QGridLayout *grid = nullptr;
    std::vector<QFrame *> cards;
};

struct Task {
    int id = 0;
    int stage = 0;         // 0 queued, 1 on the way, 2 done, 3 cancelled
    int ticks = 0;
    QString type;          // "Deliver" or "Guide"
    QFrame *card = nullptr;
    QLabel *status = nullptr;
    QPushButton *cancel = nullptr;
};

void setImageOrText(QLabel *lbl, const QString &path, const QString &fallback, const QSize &sz)
{
    QPixmap pm;
    if (!path.isEmpty())
        pm.load(path);
    if (!pm.isNull())
        lbl->setPixmap(pm.scaled(sz, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    else
        lbl->setText(fallback);
}

} // namespace

// ===========================================================================
MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::MainWindow)
{
    ui->setupUi(this);
    menuBar()->hide();
    statusBar()->hide();
    setWindowTitle(QString(kAppName) + " | Campus Assistant");
    setMinimumSize(1100, 640);
    resize(1280, 760);
    setWindowState(Qt::WindowMaximized);

    // F11 = full screen, Esc = back to maximized
    auto *fsKey = new QShortcut(QKeySequence(Qt::Key_F11), this);
    connect(fsKey, &QShortcut::activated, this, [this] {
        if (isFullScreen()) showMaximized(); else showFullScreen();
    });
    auto *escKey = new QShortcut(QKeySequence(Qt::Key_Escape), this);
    connect(escKey, &QShortcut::activated, this, [this] {
        if (isFullScreen()) showMaximized();
    });

    auto T = [](const char *s) { return QString::fromUtf8(s); };

    // ------------------------------------------------------------------
    // Campus data  (edit these lists to match your campus)
    // Place: name, building, floor, description, open hour, close hour, accessible, image
    // ------------------------------------------------------------------
    const std::vector<PlaceCategory> catalog = {
                                                 {"Academic Blocks", "BLOCKS", ":/img/cat_blocks.png", {
                                                                                                         {"Electronics Dept Office", "Main Building", "2nd Floor",
                                                                                                          "Department office, faculty cabins and the departmental notice board.",
                                                                                                          9, 17, true, ":/img/electronics_office.png"},
                                                                                                         {"Computer Dept Office", "IT Block", "1st Floor",
                                                                                                          "Department office, faculty cabins and project submissions.",
                                                                                                          9, 17, true, ":/img/computer_office.png"},
                                                                                                         {"Lecture Hall Complex", "Block C", "Ground Floor",
                                                                                                          "Large lecture halls LH-1 to LH-6 for combined classes.",
                                                                                                          8, 18, true, ":/img/lecture_halls.png"},
                                                                                                         }},
                                                 {"Labs", "LABS", ":/img/cat_labs.png", {
                                                                                          {"Embedded Systems Lab", "Electronics Block", "Ground Floor",
                                                                                           "Microcontroller kits, oscilloscopes and soldering stations.",
                                                                                           9, 17, true, ":/img/embedded_lab.png"},
                                                                                          {"Computer Lab 1", "IT Block", "Ground Floor",
                                                                                           "60 workstations for programming and simulation practicals.",
                                                                                           9, 18, true, ":/img/computer_lab.png"},
                                                                                          {"Robotics Lab", "Innovation Centre", "1st Floor",
                                                                                           "Robot arms, mobile robot platforms and a test arena.",
                                                                                           10, 18, false, ":/img/robotics_lab.png"},
                                                                                          }},
                                                 {"Administration", "ADMIN", ":/img/cat_admin.png", {
                                                                                                      {"Examination Cell", "Admin Building", "1st Floor",
                                                                                                       "Exam forms, hall tickets and result queries.",
                                                                                                       10, 16, true, ":/img/exam_cell.png"},
                                                                                                      {"Accounts Office", "Admin Building", "Ground Floor",
                                                                                                       "Fee payments, receipts and scholarship enquiries.",
                                                                                                       10, 16, true, ":/img/accounts.png"},
                                                                                                      {"Training & Placement Cell", "Admin Building", "2nd Floor",
                                                                                                       "Campus placement drives, company visits and internships.",
                                                                                                       10, 17, true, ":/img/placement.png"},
                                                                                                      {"Principal's Office", "Admin Building", "2nd Floor",
                                                                                                       "Principal's office and the meeting room.",
                                                                                                       10, 17, true, ":/img/principal.png"},
                                                                                                      }},
                                                 {"Library & Study", "LIBRARY", ":/img/cat_library.png", {
                                                                                                           {"Central Library", "Library Building", "Ground Floor",
                                                                                                            "Issue and return counter, reference books and journals.",
                                                                                                            8, 20, true, ":/img/library.png"},
                                                                                                           {"Reading Room", "Library Building", "1st Floor",
                                                                                                            "Silent study space with individual desks.",
                                                                                                            8, 22, false, ":/img/reading_room.png"},
                                                                                                           {"Digital Library", "Library Building", "2nd Floor",
                                                                                                            "E-journals, e-books and research databases on campus terminals.",
                                                                                                            9, 18, true, ":/img/digital_library.png"},
                                                                                                           }},
                                                 {"Food & Hostels", "FOOD", ":/img/cat_food.png", {
                                                                                                    {"Main Canteen", "Canteen Block", "Ground Floor",
                                                                                                     "Breakfast, lunch and snacks with indoor and outdoor seating.",
                                                                                                     8, 19, true, ":/img/canteen.png"},
                                                                                                    {"Boys Hostel Office", "Hostel 1", "Ground Floor",
                                                                                                     "Warden's office, visitor entries and room queries.",
                                                                                                     9, 18, true, ":/img/hostel1.png"},
                                                                                                    {"Girls Hostel Office", "Hostel 2", "Ground Floor",
                                                                                                     "Warden's office, visitor entries and room queries.",
                                                                                                     9, 18, true, ":/img/hostel2.png"},
                                                                                                    }},
                                                 {"Sports & Facilities", "CAMPUS", ":/img/cat_campus.png", {
                                                                                                               {"Sports Ground", "Sports Complex", "Outdoors",
                                                                                                                "Cricket, football and a 400 m running track.",
                                                                                                                6, 19, true, ":/img/ground.png"},
                                                                                                               {"Auditorium", "Cultural Block", "Ground Floor",
                                                                                                                "Seminars, college events and guest lectures.",
                                                                                                                9, 21, true, ":/img/auditorium.png"},
                                                                                                               {"Medical Room", "Admin Building", "Ground Floor",
                                                                                                                "First aid and a visiting doctor on weekdays.",
                                                                                                                9, 17, true, ":/img/medical.png"},
                                                                                                               }},
                                                 };

    // Message recipients: name, role/department, location (must match a Place name)
    const std::vector<Person> people = {
                                         {"Prof. R. Kulkarni",       "Head, Electronics Dept",  "Electronics Dept Office"},
                                         {"Dr. S. Patil",            "Computer Dept",           "Computer Dept Office"},
                                         {"Examination Cell",        "Administration",          "Examination Cell"},
                                         {"Accounts Office",         "Administration",          "Accounts Office"},
                                         {"Placement Officer",       "Training & Placement",    "Training & Placement Cell"},
                                         {"Librarian",               "Central Library",         "Central Library"},
                                         {"Boys Hostel Warden",      "Hostel 1",                "Boys Hostel Office"},
                                         {"Robotics Lab In-charge",  "Innovation Centre",       "Robotics Lab"},
                                         };

    // ------------------------------------------------------------------
    // Shared helpers
    // ------------------------------------------------------------------
    auto isOpenNow = [](int openHour, int closeHour) {
        const int h = QTime::currentTime().hour();
        return h >= openHour && h < closeHour;
    };
    auto styleStatus = [](QLabel *lbl, bool open) {
        lbl->setText(open ? "Open now" : "Closed");
        lbl->setStyleSheet(open
                               ? "background:#d9f2e6; color:#1f6f4a; border-radius:8px; padding:2px 8px; font-size:11px; font-weight:bold;"
                               : "background:#e9ecef; color:#6b7280; border-radius:8px; padding:2px 8px; font-size:11px; font-weight:bold;");
    };

    // ------------------------------------------------------------------
    // Root layout: header / pages / toast bar
    // ------------------------------------------------------------------
    auto *central = new QWidget(this);
    central->setObjectName("central");
    setCentralWidget(central);

    auto *root = new QVBoxLayout(central);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    auto *pageStack = new QStackedWidget;
    auto tabBtns = std::make_shared<std::vector<QPushButton *>>();
    QLabel *queueTabLabel = nullptr;

    // ---------------- header: logo, name, tabs, search ----------------
    auto *header = new QFrame;
    header->setObjectName("header");
    header->setFixedHeight(68);
    auto *hh = new QHBoxLayout(header);
    hh->setContentsMargins(24, 0, 24, 0);
    hh->setSpacing(12);

    auto *logo = new QLabel(QString(QString(kAppName).at(0)));
    logo->setObjectName("logo");
    logo->setFixedSize(38, 38);
    logo->setAlignment(Qt::AlignCenter);
    auto *brandName = new QLabel(kAppName);
    brandName->setObjectName("brandName");
    hh->addWidget(logo);
    hh->addWidget(brandName);
    hh->addSpacing(28);

    auto *navGroup = new QButtonGroup(this);
    navGroup->setExclusive(true);

    struct NavDef { const char *text; LineIcon::Kind kind; };
    const NavDef navDefs[] = {
                               {"Find Places",  LineIcon::Pin},
                               {"Send Message", LineIcon::Mail},
                               {"Queue",        LineIcon::List},
                               };
    int tabIndex = 0;
    for (const auto &nd : navDefs) {
        auto *btn = new QPushButton;
        btn->setObjectName("navBtn");
        btn->setCheckable(true);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setFixedSize(156, 68);
        auto *bl = new QHBoxLayout(btn);
        bl->setContentsMargins(12, 0, 12, 0);
        bl->setSpacing(6);

        auto *ic = new LineIcon(nd.kind);
        ic->setAttribute(Qt::WA_TransparentForMouseEvents);
        auto *lb = new QLabel(QString(nd.text));
        lb->setAttribute(Qt::WA_TransparentForMouseEvents);
        bl->addStretch();
        bl->addWidget(ic);
        bl->addWidget(lb);
        bl->addStretch();

        navGroup->addButton(btn);
        tabBtns->push_back(btn);
        if (tabIndex == 2)
            queueTabLabel = lb;

        auto styleNav = [ic, lb](bool on) {
            ic->setColor(on ? QColor("#ffb703") : QColor("#cfe3df"));
            lb->setStyleSheet(on
                                  ? "color:#ffb703; font-size:14px; font-weight:bold; background:transparent;"
                                  : "color:#cfe3df; font-size:14px; background:transparent;");
        };
        styleNav(false);
        QObject::connect(btn, &QPushButton::toggled, btn, styleNav);
        const int idx = tabIndex;
        QObject::connect(btn, &QPushButton::clicked, pageStack,
                         [=] { pageStack->setCurrentIndex(idx); });
        if (tabIndex == 0)
            btn->setChecked(true);
        hh->addWidget(btn);
        ++tabIndex;
    }
    hh->addStretch();

    auto *searchBox = new QFrame;
    searchBox->setObjectName("searchBox");
    searchBox->setFixedSize(300, 40);
    auto *sbl = new QHBoxLayout(searchBox);
    sbl->setContentsMargins(10, 0, 14, 0);
    sbl->setSpacing(6);
    auto *searchEdit = new QLineEdit;
    searchEdit->setObjectName("searchEdit");
    searchEdit->setPlaceholderText("Search places, buildings...");
    searchEdit->setClearButtonEnabled(true);
    sbl->addWidget(new LineIcon(LineIcon::Search, QColor("#ffb703")));
    sbl->addWidget(searchEdit, 1);
    hh->addWidget(searchBox);

    // ---------------- toast bar (confirmation after Navigate / Send) ----------------
    auto *toastBar = new QFrame;
    toastBar->setObjectName("toastBar");
    toastBar->setFixedHeight(56);
    toastBar->hide();
    auto *tb = new QHBoxLayout(toastBar);
    tb->setContentsMargins(28, 0, 28, 0);
    auto *toastText = new QLabel;
    toastText->setObjectName("toastText");
    auto *btnViewQueue = new QPushButton(QString("View Queue  ") + QChar(0x203A));
    btnViewQueue->setObjectName("btnViewQueue");
    btnViewQueue->setCursor(Qt::PointingHandCursor);
    tb->addWidget(toastText);
    tb->addStretch();
    tb->addWidget(btnViewQueue);

    auto *toastTimer = new QTimer(this);
    toastTimer->setSingleShot(true);
    connect(toastTimer, &QTimer::timeout, toastBar, &QWidget::hide);
    auto showToast = [=](const QString &msg) {
        toastText->setText(msg);
        toastBar->show();
        toastTimer->start(5000);
    };
    connect(btnViewQueue, &QPushButton::clicked, this, [=] {
        toastBar->hide();
        tabBtns->at(2)->click();
    });

    // ==================================================================
    // QUEUE PAGE
    // ==================================================================
    auto *queuePage = new QWidget;
    auto *ql = new QVBoxLayout(queuePage);
    ql->setContentsMargins(32, 24, 32, 16);
    ql->setSpacing(12);

    auto *qTop = new QHBoxLayout;
    auto *qTitle = new QLabel("Task Queue");
    qTitle->setObjectName("pageTitle");
    auto *btnClear = new QPushButton("Clear finished");
    btnClear->setObjectName("btnGhost");
    btnClear->setFixedHeight(36);
    btnClear->setCursor(Qt::PointingHandCursor);
    qTop->addWidget(qTitle);
    qTop->addStretch();
    qTop->addWidget(btnClear);
    ql->addLayout(qTop);

    auto *emptyLbl = new QLabel("No tasks yet. Send a message or tap Navigate on a place.");
    emptyLbl->setObjectName("emptyLbl");
    emptyLbl->setAlignment(Qt::AlignCenter);
    ql->addWidget(emptyLbl);

    auto *qScroll = new QScrollArea;
    qScroll->setWidgetResizable(true);
    qScroll->setFrameShape(QFrame::NoFrame);
    qScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    qScroll->viewport()->setAutoFillBackground(false);
    auto *qHost = new QWidget;
    qHost->setObjectName("queueHost");
    auto *qLayout = new QVBoxLayout(qHost);
    qLayout->setContentsMargins(0, 0, 0, 0);
    qLayout->setSpacing(10);
    qLayout->addStretch();
    qScroll->setWidget(qHost);
    ql->addWidget(qScroll, 1);

    auto tasks = std::make_shared<std::vector<Task>>();
    auto nextId = std::make_shared<int>(1);

    auto stageText = [](const Task &t) -> QString {
        switch (t.stage) {
        case 0: return "Queued";
        case 1: return "On the way";
        case 2: return t.type == "Deliver" ? "Delivered" : "Arrived";
        default: return "Cancelled";
        }
    };
    auto stageStyle = [](int stage) -> QString {
        static const char *bg[] = {"#fff3cd", "#dbeafe", "#d9f2e6", "#e9ecef"};
        static const char *fg[] = {"#8a6d00", "#1d4ed8", "#1f6f4a", "#6b7280"};
        return QString("background:%1; color:%2; border-radius:10px; padding:3px 12px; "
                       "font-weight:bold; font-size:12px;")
            .arg(QString(bg[stage]), QString(fg[stage]));
    };
    auto refreshTask = [=](Task &t) {
        t.status->setText(stageText(t));
        t.status->setStyleSheet(stageStyle(t.stage));
        t.cancel->setVisible(t.stage < 2);
    };
    auto refreshQueueInfo = [=]() {
        int active = 0;
        for (const auto &t : *tasks)
            if (t.stage < 2) ++active;
        emptyLbl->setVisible(tasks->empty());
        queueTabLabel->setText(active > 0 ? QString("Queue (%1)").arg(active) : QString("Queue"));
    };

    // ---- Hook for the real robot: send the command here ----------------
    // (serial port, TCP socket, ROS bridge, MQTT ...). For now it just prints.
    auto dispatchToRobot = [](int id, const QString &type, const QString &destination,
                              const QString &payload) {
        qDebug() << "[robot] task" << id << type << "->" << destination << payload;
    };

    auto addTask = [=](const QString &type, const QString &title, const QString &detail,
                       const QString &destination, const QString &payload, bool urgent) {
        Task t;
        t.id = (*nextId)++;
        t.type = type;
        const int id = t.id;

        auto *card = new QFrame;
        card->setObjectName("taskCard");
        auto *h = new QHBoxLayout(card);
        h->setContentsMargins(16, 12, 16, 12);
        h->setSpacing(14);

        auto *typeChip = new QLabel(type == "Deliver" ? "DELIVERY" : "GUIDE");
        typeChip->setObjectName(type == "Deliver" ? "chipDeliver" : "chipGuide");

        auto *col = new QVBoxLayout;
        col->setSpacing(2);
        auto *titleL = new QLabel(title);
        titleL->setObjectName("taskTitle");
        titleL->setWordWrap(true);
        auto *detailL = new QLabel(QString("%1   |   #%2   |   %3")
                                       .arg(detail)
                                       .arg(id)
                                       .arg(QTime::currentTime().toString("hh:mm")));
        detailL->setObjectName("taskDetail");
        detailL->setWordWrap(true);
        col->addWidget(titleL);
        col->addWidget(detailL);

        auto *status = new QLabel;
        auto *cancel = new QPushButton("Cancel");
        cancel->setObjectName("btnGhost");
        cancel->setFixedHeight(32);
        cancel->setCursor(Qt::PointingHandCursor);

        h->addWidget(typeChip, 0, Qt::AlignVCenter);
        h->addLayout(col, 1);
        h->addWidget(status, 0, Qt::AlignVCenter);
        h->addWidget(cancel, 0, Qt::AlignVCenter);

        t.card = card;
        t.status = status;
        t.cancel = cancel;
        refreshTask(t);

        // urgent tasks go ahead of waiting tasks (but not ahead of one already moving)
        int pos = static_cast<int>(tasks->size());
        if (urgent) {
            for (int k = 0; k < static_cast<int>(tasks->size()); ++k) {
                if ((*tasks)[k].stage == 0) { pos = k; break; }
            }
        }
        qLayout->insertWidget(pos, card);
        tasks->insert(tasks->begin() + pos, t);

        QObject::connect(cancel, &QPushButton::clicked, card, [=] {
            for (auto &x : *tasks) {
                if (x.id == id && x.stage < 2) {
                    x.stage = 3;
                    refreshTask(x);
                    break;
                }
            }
            refreshQueueInfo();
        });

        dispatchToRobot(id, type, destination, payload);
        refreshQueueInfo();
    };

    connect(btnClear, &QPushButton::clicked, this, [=] {
        auto &v = *tasks;
        for (auto it = v.begin(); it != v.end();) {
            if (it->stage >= 2) {
                it->card->hide();
                it->card->deleteLater();
                it = v.erase(it);
            } else {
                ++it;
            }
        }
        refreshQueueInfo();
    });

    // Simulated robot: one task at a time. Replace with real robot feedback later.
    auto *robotTimer = new QTimer(this);
    connect(robotTimer, &QTimer::timeout, this, [=] {
        for (auto &t : *tasks) {
            if (t.stage >= 2) continue;
            if (t.stage == 0) { t.stage = 1; t.ticks = 0; }
            else if (++t.ticks >= 3) { t.stage = 2; }
            refreshTask(t);
            break;
        }
        refreshQueueInfo();
    });
    robotTimer->start(3000);
    refreshQueueInfo();

    // ==================================================================
    // SEND MESSAGE PAGE
    // ==================================================================
    auto *msgPage = new QWidget;
    auto *mpl = new QHBoxLayout(msgPage);
    mpl->setContentsMargins(24, 28, 24, 24);

    auto *formCard = new QFrame;
    formCard->setObjectName("formCard");
    formCard->setFixedWidth(660);
    auto *fl = new QVBoxLayout(formCard);
    fl->setContentsMargins(30, 26, 30, 26);
    fl->setSpacing(8);

    auto *fTitle = new QLabel("Send a Message");
    fTitle->setObjectName("pageTitle");
    auto *fSub = new QLabel("The robot will carry your message to the recipient's location.");
    fSub->setObjectName("pDesc");

    auto *recipientCombo = new QComboBox;
    for (const auto &pe : people)
        recipientCombo->addItem(QString("%1  -  %2").arg(T(pe.name), T(pe.role)), T(pe.location));

    auto *msgLocCombo = new QComboBox;
    for (const auto &cat : catalog)
        for (const auto &pl : cat.items)
            msgLocCombo->addItem(T(pl.name));

    auto *priorityCombo = new QComboBox;
    priorityCombo->addItem("Normal");
    priorityCombo->addItem("Urgent (goes first in the queue)");

    auto *msgEdit = new QPlainTextEdit;
    msgEdit->setPlaceholderText("Type your message here...");
    msgEdit->setMinimumHeight(130);
    auto *counter = new QLabel("0 / 200");
    counter->setObjectName("counter");
    counter->setAlignment(Qt::AlignRight);

    auto *errorLbl = new QLabel;
    errorLbl->setObjectName("errorLbl");
    errorLbl->hide();

    auto *btnClearMsg = new QPushButton("Clear");
    btnClearMsg->setObjectName("btnGhost");
    btnClearMsg->setFixedHeight(38);
    btnClearMsg->setCursor(Qt::PointingHandCursor);
    auto *btnSend = new QPushButton("Send via Robot");
    btnSend->setObjectName("btnPrimary");
    btnSend->setFixedHeight(38);
    btnSend->setCursor(Qt::PointingHandCursor);
    auto *btnRow = new QHBoxLayout;
    btnRow->addStretch();
    btnRow->addWidget(btnClearMsg);
    btnRow->addWidget(btnSend);

    auto field = [&](const QString &label) {
        auto *l = new QLabel(label);
        l->setObjectName("fieldLabel");
        fl->addWidget(l);
    };
    fl->addWidget(fTitle);
    fl->addWidget(fSub);
    fl->addSpacing(8);
    field("To");               fl->addWidget(recipientCombo);
    field("Deliver to");       fl->addWidget(msgLocCombo);
    field("Priority");         fl->addWidget(priorityCombo);
    field("Message");          fl->addWidget(msgEdit);
    fl->addWidget(counter);
    fl->addWidget(errorLbl);
    fl->addLayout(btnRow);

    mpl->addStretch(1);
    mpl->addWidget(formCard, 0, Qt::AlignTop);
    mpl->addStretch(1);

    // recipient -> auto-select their location
    QObject::connect(recipientCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this,
                     [=](int idx) {
                         const int k = msgLocCombo->findText(recipientCombo->itemData(idx).toString());
                         if (k >= 0) msgLocCombo->setCurrentIndex(k);
                     });
    {
        const int k = msgLocCombo->findText(recipientCombo->itemData(0).toString());
        if (k >= 0) msgLocCombo->setCurrentIndex(k);
    }

    // 200 character limit + counter
    QObject::connect(msgEdit, &QPlainTextEdit::textChanged, this, [=] {
        const QString s = msgEdit->toPlainText();
        if (s.size() > 200) {
            QSignalBlocker block(msgEdit);
            msgEdit->setPlainText(s.left(200));
            msgEdit->moveCursor(QTextCursor::End);
        }
        counter->setText(QString("%1 / 200").arg(msgEdit->toPlainText().size()));
        errorLbl->hide();
    });
    QObject::connect(btnClearMsg, &QPushButton::clicked, msgEdit, &QPlainTextEdit::clear);

    QObject::connect(btnSend, &QPushButton::clicked, this, [=] {
        const QString text = msgEdit->toPlainText().trimmed();
        if (text.isEmpty()) {
            errorLbl->setText("Please type a message before sending.");
            errorLbl->show();
            return;
        }
        const bool urgent = priorityCombo->currentIndex() == 1;
        const QString who = recipientCombo->currentText();
        const QString loc = msgLocCombo->currentText();
        QString preview = text.left(60);
        if (text.size() > 60) preview += "...";

        addTask("Deliver",
                QString("%1Message to %2").arg(QString(urgent ? "URGENT: " : ""), who),
                QString("Deliver to %1   |   \"%2\"").arg(loc, preview),
                loc, text, urgent);
        msgEdit->clear();
        showToast(QString("Message queued for delivery to %1").arg(loc));
    });

    // ==================================================================
    // FIND PLACES PAGE
    // ==================================================================
    auto *placesPage = new QWidget;
    auto *bodyLayout = new QHBoxLayout(placesPage);
    bodyLayout->setContentsMargins(0, 0, 0, 0);
    bodyLayout->setSpacing(0);

    auto catBtns = std::make_shared<std::vector<QPushButton *>>();
    auto pages = std::make_shared<std::vector<Page>>();

    // ---------------- place card ----------------
    auto makePlaceCard = [=](const Place &pl) -> QFrame * {
        const QString name = T(pl.name);
        const QString where = QString("%1, %2").arg(T(pl.building), T(pl.floor));

        auto *card = new QFrame;
        card->setObjectName("placeCard");
        card->setProperty("openHour", pl.openHour);
        card->setProperty("closeHour", pl.closeHour);
        card->setProperty("acc", pl.accessible);
        card->setProperty("searchKey",
                          (name + " " + T(pl.building) + " " + T(pl.floor) + " " + T(pl.desc)).toLower());

        auto *h = new QHBoxLayout(card);
        h->setContentsMargins(18, 14, 14, 14);
        h->setSpacing(16);

        auto *col = new QVBoxLayout;
        col->setContentsMargins(0, 0, 0, 0);
        col->setSpacing(6);

        auto *chips = new QHBoxLayout;
        chips->setSpacing(6);
        auto *locChip = new QLabel(QString("%1  |  %2").arg(T(pl.building), T(pl.floor)));
        locChip->setObjectName("chipLoc");
        auto *statusChip = new QLabel;
        statusChip->setObjectName("chipStatus");
        styleStatus(statusChip, isOpenNow(pl.openHour, pl.closeHour));
        chips->addWidget(locChip);
        chips->addWidget(statusChip);
        if (pl.accessible) {
            auto *acc = new QLabel("Accessible");
            acc->setObjectName("chipAcc");
            chips->addWidget(acc);
        }
        chips->addStretch();

        auto *nameL = new QLabel(name);
        nameL->setObjectName("pName");
        nameL->setWordWrap(true);
        auto *descL = new QLabel(T(pl.desc));
        descL->setObjectName("pDesc");
        descL->setWordWrap(true);
        auto *hoursL = new QLabel(QString("Hours: %1:00 - %2:00")
                                      .arg(pl.openHour, 2, 10, QChar('0'))
                                      .arg(pl.closeHour, 2, 10, QChar('0')));
        hoursL->setObjectName("pHours");

        auto *btnRow2 = new QHBoxLayout;
        btnRow2->setSpacing(8);
        auto *btnGo = new QPushButton("Navigate");
        btnGo->setObjectName("btnPrimary");
        btnGo->setFixedHeight(36);
        btnGo->setCursor(Qt::PointingHandCursor);
        auto *btnMsg = new QPushButton("Message here");
        btnMsg->setObjectName("btnGhost");
        btnMsg->setFixedHeight(36);
        btnMsg->setCursor(Qt::PointingHandCursor);
        btnRow2->addWidget(btnGo);
        btnRow2->addWidget(btnMsg);
        btnRow2->addStretch();

        col->addLayout(chips);
        col->addWidget(nameL);
        col->addWidget(descL);
        col->addWidget(hoursL);
        col->addStretch(1);
        col->addLayout(btnRow2);

        h->addLayout(col, 1);
        h->addWidget(new ImageBox(T(pl.image)));

        QObject::connect(btnGo, &QPushButton::clicked, card, [=] {
            addTask("Guide", QString("Guide to %1").arg(name), where, name, QString(), false);
            showToast(QString("Navigation to %1 added to the queue").arg(name));
        });
        QObject::connect(btnMsg, &QPushButton::clicked, card, [=] {
            const int k = msgLocCombo->findText(name);
            if (k >= 0) msgLocCombo->setCurrentIndex(k);
            tabBtns->at(1)->click();
        });
        return card;
    };

    // ---------------- sidebar ----------------
    auto *sidebar = new QScrollArea;
    sidebar->setObjectName("sidebar");
    sidebar->setFixedWidth(232);
    sidebar->setWidgetResizable(true);
    sidebar->setFrameShape(QFrame::NoFrame);
    sidebar->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    sidebar->viewport()->setAutoFillBackground(false);
    auto *sideHost = new QWidget;
    sideHost->setObjectName("sideHost");
    auto *sideLayout = new QVBoxLayout(sideHost);
    sideLayout->setContentsMargins(14, 16, 14, 16);
    sideLayout->setSpacing(10);
    sidebar->setWidget(sideHost);

    auto *divider = new QFrame;
    divider->setObjectName("divider");
    divider->setFixedWidth(1);

    // ---------------- right pane: filters + category pages ----------------
    auto *rightPane = new QWidget;
    auto *rightLayout = new QVBoxLayout(rightPane);
    rightLayout->setContentsMargins(20, 16, 0, 0);
    rightLayout->setSpacing(12);

    auto *filterRow = new QHBoxLayout;
    filterRow->setSpacing(12);
    auto makePill = [&](const QString &text, const QColor &col) -> ToggleSwitch * {
        auto *pill = new QFrame;
        pill->setObjectName("pill");
        auto *ph = new QHBoxLayout(pill);
        ph->setContentsMargins(16, 6, 12, 6);
        ph->setSpacing(10);
        auto *lbl = new QLabel(text);
        lbl->setObjectName("pillText");
        auto *sw = new ToggleSwitch(col);
        ph->addWidget(lbl);
        ph->addWidget(sw);
        filterRow->addWidget(pill);
        return sw;
    };
    auto *openSwitch = makePill("Open now", QColor("#2e9d3a"));
    auto *accSwitch = makePill("Accessible", QColor("#2f4fb5"));
    filterRow->addStretch();
    rightLayout->addLayout(filterRow);

    auto *stack = new QStackedWidget;
    rightLayout->addWidget(stack, 1);

    auto *catGroup = new QButtonGroup(this);
    catGroup->setExclusive(true);

    int i = 0;
    for (const auto &cat : catalog) {
        auto *btn = new QPushButton;
        btn->setObjectName("catBtn");
        btn->setCheckable(true);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setFixedSize(204, 66);
        auto *bl = new QHBoxLayout(btn);
        bl->setContentsMargins(10, 8, 10, 8);
        bl->setSpacing(10);

        auto *ci = new QLabel;
        ci->setAlignment(Qt::AlignCenter);
        ci->setFixedSize(52, 44);
        ci->setAttribute(Qt::WA_TransparentForMouseEvents);
        setImageOrText(ci, T(cat.image), T(cat.shortText), QSize(52, 44));

        auto *cn = new QLabel(T(cat.name));
        cn->setAlignment(Qt::AlignVCenter | Qt::AlignLeft);
        cn->setWordWrap(true);
        cn->setAttribute(Qt::WA_TransparentForMouseEvents);

        bl->addWidget(ci);
        bl->addWidget(cn, 1);
        catGroup->addButton(btn);
        sideLayout->addWidget(btn);
        catBtns->push_back(btn);

        auto styleCat = [ci, cn](bool on) {
            cn->setStyleSheet(on
                                  ? "color:#ffffff; font-weight:bold; font-size:13px; background:transparent;"
                                  : "color:#12343b; font-weight:bold; font-size:13px; background:transparent;");
            ci->setStyleSheet(on
                                  ? "color:#12343b; font-weight:bold; font-size:11px; background:#ffb703; border-radius:10px;"
                                  : "color:#1f6f6a; font-weight:bold; font-size:11px; background:#e3f3f0; border-radius:10px;");
        };
        styleCat(false);
        QObject::connect(btn, &QPushButton::toggled, btn, styleCat);
        QObject::connect(btn, &QPushButton::clicked, stack, [=] { stack->setCurrentIndex(i); });

        auto *scroll = new QScrollArea;
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        scroll->viewport()->setAutoFillBackground(false);
        auto *host = new QWidget;
        host->setObjectName("pageHost");
        auto *grid = new QGridLayout(host);
        grid->setContentsMargins(0, 4, 20, 20);
        grid->setHorizontalSpacing(18);
        grid->setVerticalSpacing(18);
        grid->setColumnStretch(0, 1);
        grid->setColumnStretch(1, 1);
        grid->setRowStretch(50, 1);
        scroll->setWidget(host);
        stack->addWidget(scroll);

        Page page;
        page.grid = grid;
        for (const auto &pl : cat.items)
            page.cards.push_back(makePlaceCard(pl));
        pages->push_back(page);

        if (i == 0)
            btn->setChecked(true);
        ++i;
    }
    sideLayout->addStretch();

    // ---------------- filters + search ----------------
    auto applyFilter = [=]() {
        const bool onlyOpen = openSwitch->isChecked();
        const bool onlyAcc = accSwitch->isChecked();
        const QString q = searchEdit->text().trimmed().toLower();

        std::vector<int> visibleCount;
        for (auto &pg : *pages) {
            for (auto *c : pg.cards)
                pg.grid->removeWidget(c);
            int idx = 0;
            for (auto *c : pg.cards) {
                const bool open = isOpenNow(c->property("openHour").toInt(),
                                            c->property("closeHour").toInt());
                if (auto *st = c->findChild<QLabel *>("chipStatus"))
                    styleStatus(st, open);
                const bool show = (!onlyOpen || open)
                                  && (!onlyAcc || c->property("acc").toBool())
                                  && (q.isEmpty() || c->property("searchKey").toString().contains(q));
                c->setVisible(show);
                if (show) {
                    pg.grid->addWidget(c, idx / 2, idx % 2);
                    ++idx;
                }
            }
            visibleCount.push_back(idx);
        }

        // while searching, jump to the first category that has a match
        if (!q.isEmpty()) {
            const int cur = stack->currentIndex();
            if (cur >= 0 && visibleCount[cur] == 0) {
                for (size_t k = 0; k < visibleCount.size(); ++k) {
                    if (visibleCount[k] > 0) {
                        (*catBtns)[k]->click();
                        break;
                    }
                }
            }
        }
    };
    QObject::connect(openSwitch, &QAbstractButton::toggled, this, [=](bool) { applyFilter(); });
    QObject::connect(accSwitch, &QAbstractButton::toggled, this, [=](bool) { applyFilter(); });
    QObject::connect(searchEdit, &QLineEdit::textChanged, this, [=](const QString &t) {
        if (!t.trimmed().isEmpty() && pageStack->currentIndex() != 0)
            tabBtns->at(0)->click();
        applyFilter();
    });
    applyFilter();

    // refresh "Open now / Closed" every minute
    auto *clockTimer = new QTimer(this);
    connect(clockTimer, &QTimer::timeout, this, [=] { applyFilter(); });
    clockTimer->start(60000);

    bodyLayout->addWidget(sidebar);
    bodyLayout->addWidget(divider);
    bodyLayout->addWidget(rightPane, 1);

    // ------------------------------------------------------------------
    pageStack->addWidget(placesPage);   // 0
    pageStack->addWidget(msgPage);      // 1
    pageStack->addWidget(queuePage);    // 2

    root->addWidget(header);
    root->addWidget(pageStack, 1);
    root->addWidget(toastBar);

    // ------------------------------------------------------------------
    // Style
    // ------------------------------------------------------------------
    central->setStyleSheet(R"(
        QWidget#central { background: #f3f6f5; }

        QFrame#header { background: #12343b; }
        QLabel#logo {
            background: #ffb703; color: #12343b; font-size: 20px;
            font-weight: bold; border-radius: 10px;
        }
        QLabel#brandName { color: #ffffff; font-size: 22px; font-weight: bold; }
        QPushButton#navBtn {
            background: transparent; border: none; border-bottom: 3px solid transparent;
        }
        QPushButton#navBtn:checked { border-bottom: 3px solid #ffb703; }
        QFrame#searchBox { background: #1d4a52; border-radius: 20px; }
        QLineEdit#searchEdit {
            background: transparent; border: none; color: #ffffff; font-size: 14px;
        }

        QScrollArea, QWidget#sideHost, QWidget#pageHost, QWidget#queueHost {
            background: transparent; border: none;
        }
        QFrame#divider { background: #d5dfdc; }

        QPushButton#catBtn {
            background: #ffffff; border: 1px solid #dbe5e2; border-radius: 14px;
        }
        QPushButton#catBtn:hover { border: 1px solid #1f6f6a; }
        QPushButton#catBtn:checked { background: #1f6f6a; border: 1px solid #1f6f6a; }

        QFrame#pill { background: #ffffff; border: 1px solid #cfdcd8; border-radius: 20px; }
        QLabel#pillText { color: #12343b; font-size: 13px; font-weight: bold; }

        QFrame#placeCard {
            background: #ffffff; border: 1px solid #e3ebe8; border-radius: 16px;
        }
        QLabel#chipLoc {
            background: #e3f4ee; color: #1f6f6a; border-radius: 8px;
            padding: 2px 8px; font-size: 11px; font-weight: bold;
        }
        QLabel#chipAcc {
            background: #e8eefc; color: #2f4fb5; border-radius: 8px;
            padding: 2px 8px; font-size: 11px; font-weight: bold;
        }
        QLabel#pName { color: #12343b; font-size: 18px; font-weight: bold; }
        QLabel#pDesc { color: #5f716d; font-size: 13px; }
        QLabel#pHours { color: #12343b; font-size: 12px; font-weight: bold; }

        QPushButton#btnPrimary {
            background: #e76f51; color: #ffffff; border: none; border-radius: 18px;
            font-size: 14px; font-weight: bold; padding: 0 20px;
        }
        QPushButton#btnPrimary:hover { background: #d65f41; }
        QPushButton#btnGhost {
            background: #ffffff; color: #12343b; border: 1px solid #bfd0cc;
            border-radius: 18px; font-weight: bold; padding: 0 16px;
        }
        QPushButton#btnGhost:hover { border: 1px solid #1f6f6a; color: #1f6f6a; }

        QLabel#pageTitle { color: #12343b; font-size: 24px; font-weight: bold; }
        QFrame#formCard {
            background: #ffffff; border: 1px solid #e3ebe8; border-radius: 18px;
        }
        QLabel#fieldLabel { color: #12343b; font-weight: bold; font-size: 13px; margin-top: 6px; }
        QComboBox, QPlainTextEdit {
            background: #ffffff; border: 1px solid #cfdcd8; border-radius: 10px;
            padding: 8px 10px; font-size: 14px; color: #12343b;
        }
        QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #1f6f6a; }
        QComboBox QAbstractItemView {
            background: #ffffff; color: #12343b;
            selection-background-color: #e3f4ee; selection-color: #12343b;
        }
        QLabel#counter { color: #8a9a97; font-size: 12px; }
        QLabel#errorLbl { color: #c4452a; font-weight: bold; }

        QFrame#taskCard {
            background: #ffffff; border: 1px solid #e3ebe8; border-radius: 14px;
        }
        QLabel#taskTitle { color: #12343b; font-weight: bold; font-size: 15px; }
        QLabel#taskDetail { color: #5f716d; font-size: 12px; }
        QLabel#chipDeliver {
            background: #fde8e2; color: #c4452a; border-radius: 8px;
            padding: 3px 10px; font-size: 11px; font-weight: bold;
        }
        QLabel#chipGuide {
            background: #e3f4ee; color: #1f6f6a; border-radius: 8px;
            padding: 3px 10px; font-size: 11px; font-weight: bold;
        }
        QLabel#emptyLbl { color: #7a8c88; font-size: 15px; padding: 40px; }

        QFrame#toastBar { background: #1f6f6a; }
        QLabel#toastText { color: #ffffff; font-size: 15px; font-weight: bold; }
        QPushButton#btnViewQueue {
            background: #ffb703; color: #12343b; border: none;
            border-radius: 18px; padding: 9px 22px; font-weight: bold;
        }
    )");
}

MainWindow::~MainWindow()
{
    delete ui;
}
