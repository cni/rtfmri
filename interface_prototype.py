import sys
import logging
import argparse
from Queue import Queue, Empty
from bokeh.plotting import figure, output_server, cursession, show, VBox
import seaborn as sns


logging.basicConfig()
logger = logging.getLogger("rtfmri")


from rtfmri import ScannerInterface, MotionAnalyzer, setup_exit_handler

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-hostname", default="cnimr")
    parser.add_argument("-port", default=21, type=int)
    parser.add_argument("-username", default="")
    parser.add_argument("-password", default="")
    parser.add_argument("-base_dir", default="/export/home1/sdc_image_pool/images")
    parser.add_argument("-debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    output_server("rtfmri_prototype")

    rot_p = figure(plot_height=250, plot_width=700,
                   tools="", title="Rotation")

    rot_colors = map(sns.mpl.colors.rgb2hex, sns.color_palette("Reds_d", 3))
    for ax, color in zip("xyz", rot_colors):
        rot_p.line([], [], name="rot_" + ax,
                   color=color, line_width=2, legend=ax)

    trans_p = figure(plot_height=250, plot_width=700,
                   tools="", title="Translation")

    trans_colors = map(sns.mpl.colors.rgb2hex, sns.color_palette("Blues_d", 3))
    for ax, color in zip("xyz", trans_colors):
        trans_p.line([], [], name="trans_" + ax,
                     color=color, line_width=2, legend=ax)

    rms_p = figure(plot_height=250, plot_width=700,
                   tools="", title="Displacement")

    rms_colors = map(sns.mpl.colors.rgb2hex, sns.color_palette("Greens_d", 2))
    for kind, color in zip(["ref", "pre"], rms_colors):
        rms_p.line([], [], name="rms_" + kind,
                     color=color, line_width=2, legend=kind)

    scanner = ScannerInterface(hostname=args.hostname, port=args.port,
                               username=args.username, password=args.password,
                               base_dir=args.base_dir)
    result_q = Queue()
    rtmotion = MotionAnalyzer(scanner, result_q)

    setup_exit_handler(scanner, rtmotion)

    scanner.start()
    rtmotion.start()

    show(VBox(rot_p, trans_p, rms_p))

    while True:
        try:
            result = result_q.get(timeout=1)
            next_x = result["vol_number"]

            for fig, kind in zip([rot_p, trans_p], ["rot", "trans"]):
                for ax in "xyz":

                    ds = fig.select({"name": kind + "_" + ax})[0].data_source

                    if result["new_acquisition"]:
                        x = [next_x]
                    else:
                        x = ds.data["x"]
                        x.append(next_x)
                    ds.data["x"] = x

                    name = kind + "_" + ax
                    next_y = result[name]
                    if result["new_acquisition"]:
                        y = [result[name]]
                    else:
                        y = ds.data["y"]
                        y.append(result[name])
                    ds.data["y"] = y

                    cursession().store_objects(ds)

                fig.x_range.end = result["ntp"]
                cursession().store_objects(fig)

            for kind in ["ref", "pre"]:

                ds = rms_p.select({"name": "rms_" + kind})[0].data_source

                if result["new_acquisition"]:
                    x = [next_x]
                else:
                    x = ds.data["x"]
                    x.append(next_x)
                ds.data["x"] = x

                name = "rms_" + kind
                next_y = result[name]
                if result["new_acquisition"]:
                    y = [result[name]]
                else:
                    y = ds.data["y"]
                    y.append(result[name])
                ds.data["y"] = y

                cursession().store_objects(ds)

            rms_p.x_range.end = result["ntp"]
            cursession().store_objects(rms_p)

        except Empty:
            pass
        #except:
        #    scanner.shutdown()
        #    raise
