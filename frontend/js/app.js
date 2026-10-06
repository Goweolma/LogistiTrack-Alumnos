

let shipments = [

    {
        guide: "RAYO-2026-00125",
        destination: "Guadalajara, Jal.",
        date: "05 Oct 2026",
        status: "transit"
    },

    {
        guide: "RAYO-2026-00118",
        destination: "León, Gto.",
        date: "03 Oct 2026",
        status: "delivered"
    },

    {
        guide: "RAYO-2026-00131",
        destination: "CDMX",
        date: "05 Oct 2026",
        status: "pending"
    }

];


// ------------------------------------------
// ELEMENTOS DEL DOM
// ------------------------------------------

const trackingInput = document.getElementById("trackingInput");
const trackBtn = document.getElementById("trackBtn");

const trackingResult = document.getElementById("trackingResult");

const resultGuide = document.getElementById("resultGuide");
const resultStatus = document.getElementById("resultStatus");

const progressFill = document.getElementById("progressFill");

const shipmentSearch =
    document.getElementById("shipmentSearch");

const statusFilter =
    document.getElementById("statusFilter");

const shipmentsTable =
    document.getElementById("shipmentsTable");


// ------------------------------------------
// RASTREAR PAQUETE
// ------------------------------------------

function trackPackage(guide) {

    guide = guide.trim().toUpperCase();

    if (guide === "") {

        alert("Ingresa un número de guía.");

        return;
    }


    const shipment = shipments.find(
        item => item.guide === guide
    );


    if (!shipment) {

        alert(
            "No encontramos un paquete con esa guía."
        );

        return;
    }


    // Mostrar sección

    trackingResult.style.display = "block";


    // Actualizar número de guía

    resultGuide.textContent =
        shipment.guide;


    // Actualizar estado

    updateTrackingStatus(
        shipment.status
    );


    // Ir al seguimiento

    document.getElementById(
        "seguimiento"
    ).scrollIntoView({
        behavior: "smooth"
    });

}


// ------------------------------------------
// ACTUALIZAR ESTADO
// ------------------------------------------

function updateTrackingStatus(status) {

    resultStatus.className = "status";


    if (status === "pending") {

        resultStatus.classList.add(
            "status-pending"
        );

        resultStatus.textContent =
            "⏳ Pendiente";


        progressFill.style.width = "20%";

    }


    else if (status === "transit") {

        resultStatus.classList.add(
            "status-transit"
        );

        resultStatus.textContent =
            "🚚 En tránsito";


        progressFill.style.width = "66%";

    }


    else if (status === "delivered") {

        resultStatus.classList.add(
            "status-delivered"
        );

        resultStatus.textContent =
            "✓ Entregado";


        progressFill.style.width = "100%";

    }

}


// ------------------------------------------
// BOTÓN RASTREAR
// ------------------------------------------

trackBtn.addEventListener(
    "click",
    () => {

        trackPackage(
            trackingInput.value
        );

    }
);


// ------------------------------------------
// ENTER EN BUSCADOR
// ------------------------------------------

trackingInput.addEventListener(
    "keypress",
    event => {

        if (event.key === "Enter") {

            trackPackage(
                trackingInput.value
            );

        }

    }
);


// ------------------------------------------
// BOTONES "VER" DE LA TABLA
// ------------------------------------------

function activateTrackingButtons() {

    const buttons =
        document.querySelectorAll(
            ".track-shipment"
        );


    buttons.forEach(button => {

        button.addEventListener(
            "click",
            () => {

                const guide =
                    button.dataset.guide;

                trackingInput.value =
                    guide;

                trackPackage(guide);

            }
        );

    });

}

activateTrackingButtons();


// ------------------------------------------
// BUSCADOR DE ENVÍOS
// ------------------------------------------

shipmentSearch.addEventListener(
    "input",
    filterShipments
);


// ------------------------------------------
// FILTRO POR ESTADO
// ------------------------------------------

statusFilter.addEventListener(
    "change",
    filterShipments
);


// ------------------------------------------
// FILTRAR ENVÍOS
// ------------------------------------------

function filterShipments() {

    const search =
        shipmentSearch.value
            .toUpperCase()
            .trim();


    const status =
        statusFilter.value;


    const filtered =
        shipments.filter(shipment => {

            const matchesSearch =
                shipment.guide
                    .includes(search);


            const matchesStatus =
                status === "all" ||
                shipment.status === status;


            return (
                matchesSearch &&
                matchesStatus
            );

        });


    renderShipments(filtered);

}


// ------------------------------------------
// GENERAR TABLA
// ------------------------------------------

function renderShipments(data) {

    shipmentsTable.innerHTML = "";


    if (data.length === 0) {

        shipmentsTable.innerHTML = `

            <tr>

                <td
                    colspan="5"
                    style="text-align:center;"
                >
                    No se encontraron envíos.
                </td>

            </tr>

        `;

        return;
    }


    data.forEach(shipment => {

        let statusHTML = "";


        if (shipment.status === "transit") {

            statusHTML = `
                <span class="status status-transit">
                    🚚 En tránsito
                </span>
            `;

        }


        else if (shipment.status === "delivered") {

            statusHTML = `
                <span class="status status-delivered">
                    ✓ Entregado
                </span>
            `;

        }


        else {

            statusHTML = `
                <span class="status status-pending">
                    ⏳ Pendiente
                </span>
            `;

        }


        shipmentsTable.innerHTML += `

            <tr>

                <td>
                    <strong>
                        ${shipment.guide}
                    </strong>
                </td>

                <td>
                    ${shipment.destination}
                </td>

                <td>
                    ${shipment.date}
                </td>

                <td>
                    ${statusHTML}
                </td>

                <td>

                    <button
                        class="table-btn track-shipment"
                        data-guide="${shipment.guide}"
                    >
                        Ver
                    </button>

                </td>

            </tr>

        `;

    });


    activateTrackingButtons();

}


// ------------------------------------------
// MODAL CREAR ENVÍO
// ------------------------------------------

const shipmentModal =
    document.getElementById(
        "shipmentModal"
    );


const newShipmentBtn =
    document.getElementById(
        "newShipmentBtn"
    );


const createShipmentBtn =
    document.getElementById(
        "createShipmentBtn"
    );


const closeModal =
    document.getElementById(
        "closeModal"
    );


newShipmentBtn.addEventListener(
    "click",
    () => {

        shipmentModal.classList.add(
            "show"
        );

    }
);


createShipmentBtn.addEventListener(
    "click",
    () => {

        shipmentModal.classList.add(
            "show"
        );

    }
);


closeModal.addEventListener(
    "click",
    () => {

        shipmentModal.classList.remove(
            "show"
        );

    }
);


// ------------------------------------------
// CERRAR MODAL AL DAR CLICK AFUERA
// ------------------------------------------

shipmentModal.addEventListener(
    "click",
    event => {

        if (
            event.target ===
            shipmentModal
        ) {

            shipmentModal.classList.remove(
                "show"
            );

        }

    }
);


// ------------------------------------------
// CREAR ENVÍO
// ------------------------------------------

const shipmentForm =
    document.getElementById(
        "shipmentForm"
    );


shipmentForm.addEventListener(
    "submit",
    event => {

        event.preventDefault();


        const destination =
            document.getElementById(
                "city"
            ).value;


        // Generar guía

        const guide =
            generateTrackingNumber();


        // Crear objeto

        const newShipment = {

            guide: guide,

            destination: destination,

            date: new Date()
                .toLocaleDateString(
                    "es-MX"
                ),

            status: "pending"

        };


        // Agregar al arreglo

        shipments.unshift(
            newShipment
        );


        // Actualizar tabla

        renderShipments(
            shipments
        );


        // Actualizar estadísticas

        updateStatistics();


        // Cerrar modal

        shipmentModal.classList.remove(
            "show"
        );


        // Limpiar formulario

        shipmentForm.reset();


        // Mostrar mensaje

        alert(
            `¡Envío creado!\n\nNúmero de guía: ${guide}`
        );

    }
);


// ------------------------------------------
// GENERAR NÚMERO DE GUÍA
// ------------------------------------------

function generateTrackingNumber() {

    const random =
        Math.floor(
            10000 +
            Math.random() * 90000
        );


    return `RAYO-2026-${random}`;

}


// ------------------------------------------
// ACTUALIZAR ESTADÍSTICAS
// ------------------------------------------

function updateStatistics() {

    const total =
        shipments.length;


    const active =
        shipments.filter(
            shipment =>
                shipment.status ===
                "transit"
        ).length;


    document.getElementById(
        "totalShipments"
    ).textContent = total;


    document.getElementById(
        "activeShipments"
    ).textContent = active;

}


// ------------------------------------------
// BOTÓN DE ACTUALIZAR
// ------------------------------------------

document.getElementById(
    "refreshBtn"
).addEventListener(
    "click",
    () => {

        updateStatistics();

        alert(
            "Información actualizada."
        );

    }
);


// ------------------------------------------
// BOTÓN DE RASTREAR DEL HERO
// ------------------------------------------

document.getElementById(
    "heroTrackBtn"
).addEventListener(
    "click",
    () => {

        document.getElementById(
            "seguimiento"
        ).scrollIntoView({
            behavior: "smooth"
        });


        setTimeout(
            () => trackingInput.focus(),
            500
        );

    }
);


// ------------------------------------------
// NOTIFICACIONES
// ------------------------------------------

const notificationBtn =
    document.getElementById(
        "notificationBtn"
    );


const notificationPanel =
    document.getElementById(
        "notificationPanel"
    );


const closeNotifications =
    document.getElementById(
        "closeNotifications"
    );


notificationBtn.addEventListener(
    "click",
    () => {

        notificationPanel.classList.toggle(
            "show"
        );

    }
);


closeNotifications.addEventListener(
    "click",
    () => {

        notificationPanel.classList.remove(
            "show"
        );

    }
);


// ------------------------------------------
// CERRAR NOTIFICACIONES AL HACER CLICK AFUERA
// ------------------------------------------

document.addEventListener(
    "click",
    event => {

        if (
            !notificationPanel.contains(
                event.target
            ) &&
            !notificationBtn.contains(
                event.target
            )
        ) {

            notificationPanel.classList.remove(
                "show"
            );

        }

    }
);


// ------------------------------------------
// INICIALIZAR
// ------------------------------------------

renderShipments(
    shipments
);

updateStatistics();

console.log(
    "⚡ Rayo iniciado correctamente."
);
