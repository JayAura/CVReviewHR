(function() {
    if (typeof Dropzone === 'undefined') {
        console.error('Dropzone is not defined. Ensure dropzone.min.js is loaded before this script.');
        return;
    }

    // Always set autoDiscover to false to prevent Dropzone from auto-initializing elements.
   Dropzone.autoDiscover = false;
   document.addEventListener('DOMContentLoaded', function () {
    if (Dropzone.instances.length > 0) {
        Dropzone.instances.forEach(z => z.destroy());
    }

    const dz = new Dropzone("#quick-cv-dropzone", {
        url: "/upload_files",
        paramName: "files[]",
        maxFilesize: 16,
        uploadMultiple: true,
        parallelUploads: 10,
        maxFiles: 50,
        acceptedFiles: ".pdf,.doc,.docx,.txt",
        addRemoveLinks: true,
        autoProcessQueue: true,
        dictDefaultMessage: "Drop files here or click to upload",
        init: function () {
            const submitBtn = document.getElementById('quick-submit-btn');

            this.on("addedfile", () => {
                document.querySelector('.file-count-container').style.display = '';
                document.getElementById('file-count').innerText = this.files.length;
                submitBtn.disabled = false;
            });

            this.on("removedfile", () => {
                const count = this.files.length;
                document.getElementById('file-count').innerText = count;
                if (count === 0) {
                    document.querySelector('.file-count-container').style.display = 'none';
                    submitBtn.disabled = true;
                }
            });

            this.on("successmultiple", (files, response) => {
                if (response && response.session_id) {
                    window.location.href = "/results/" + response.session_id;
                }
            });

            this.on("error", function (file, errorMessage, xhr) {
                let message = errorMessage;
                if (xhr?.response) {
                    try {
                        let json = JSON.parse(xhr.response);
                        if (json.error) message = json.error;
                    } catch (e) {}
                }
                alert("Upload error: " + message);
            });

            submitBtn.addEventListener('click', function () {
                dz.processQueue();
            });
        }
    });
});