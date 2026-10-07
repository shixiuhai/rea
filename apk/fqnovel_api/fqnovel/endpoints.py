"""Discovered fqnovel (com.dragon.read) HTTP endpoints and request fields.

Endpoint paths come from ``@RpcOperation`` annotations on the Retrofit
interfaces (``com.dragon.read.rpc.rpc.c$a`` -> BookApiService,
``com.dragon.read.rpc.rpc.g6$a`` -> ReaderApiService) and from the KMP
generated proxy classes (``com.dragon.read.kmprpc.reader.saas.rpc.n``).

Business field names come from the kotlinx.serialization descriptors of the
request model classes (e.g. ``BookstoreTabRequest$a`` -> addElement names).
"""

from __future__ import annotations

from typing import Dict, List

from . import config


def _v(path: str, version: str = None) -> str:
    return path.replace("v:version", "v" + (version or config.API_VERSION))


# --- Book list -------------------------------------------------------------
BOOK_LIST = {
    # GET /reading/bookapi/bookstore/homepage/v1/   (request has no fields)
    "store_home": _v("/reading/bookapi/bookstore/homepage/v:version/"),
    # GET /reading/bookapi/bookmall/tab/v1/
    "mall_tab": _v("/reading/bookapi/bookmall/tab/v:version/"),
    # GET /reading/bookapi/category/booklist/v1/
    "category_booklist": _v("/reading/bookapi/category/booklist/v:version/"),
    # GET /reading/bookapi/book_extra/v1/   (open, verified working)
    "book_extra": _v("/reading/bookapi/book_extra/v:version/"),
}

# --- Book search -----------------------------------------------------------
BOOK_SEARCH = {
    # GET /reading/bookapi/search/page/v1/
    "search_page": _v("/reading/bookapi/search/page/v:version/"),
    # GET /reading/bookapi/search/search/v1/
    "search": _v("/reading/bookapi/search/search/v:version/"),
    # GET /reading/bookapi/search/suggest/v1/
    "suggest": _v("/reading/bookapi/search/suggest/v:version/"),
}

# --- Content / download ----------------------------------------------------
DOWNLOAD = {
    # GET /reading/reader/full/v1/       single chapter
    "reader_full": _v("/reading/reader/full/v:version/"),
    # GET /reading/reader/batch_full/v1/ batch chapters (offline download)
    "reader_batch_full": _v("/reading/reader/batch_full/v:version/"),
    # GET /reading/reader/newfull/v1/
    "reader_newfull": _v("/reading/reader/newfull/v:version/"),
}

# --- Detail / directory (helper, gateway-gated) ----------------------------
MISC = {
    "book_detail": _v("/reading/bookapi/detail/v:version/"),
    "directory_all_items": _v("/reading/bookapi/directory/all_items/v:version/"),
}

# --- Serialized request field names ----------------------------------------
# mall_tab  <- com.dragon.read.rpc.model.BookstoreTabRequest (83 fields)
MALL_TAB_FIELDS: List[str] = [
    "tab_index", "last_tab_index", "tab_type", "last_tab_type", "session_id",
    "offset", "current_name", "pad_column_cover", "pad_column_detail", "gd_label",
    "app_mode", "client_req_type", "extra", "cold_start_age_preference",
    "cold_start_gd", "cold_start_is_double_gd", "stream_count", "req_rank_algo",
    "req_rank_category_id", "client_template", "selected_items",
    "unlimited_short_series_next_offset", "unlimited_short_series_change_type",
    "classic_tab_style", "lore_tab_style", "version_tag", "ClickedContent",
    "recent_impr_gid", "enable_search_box_collapse", "page_entry_time",
    "bottom_tab_type", "ug_task_params", "auth_aweme", "card_list",
    "client_fetch_unlimited_mode", "ecom_feed_post_back",
    "ecom_feed_impression_params", "ecom_page_name", "ecom_refresh_type",
    "ecom_impression_start_time", "client_info", "image_shrink_datas",
    "filter_ids", "image_shrink_datas_str", "cold_start_session",
    "screen_width_px", "refresh_action_info", "landing_bottom_tab_type",
    "after_genre_preference_popup", "session_uuid", "from", "book_id",
    "auth_backward", "tab_version", "last_search_query",
    "last_search_query_source", "last_search_query_from_rec", "device_level",
    "last_view_series_id", "video_type_preferences_str",
    "first_use_category_select", "biz_config_ctx_infos", "recommend_extra",
    "disable_digg_stat", "last_session_video_tab_type",
    "immersive_consumed_book_id", "push_series_id", "push_video_id",
    "migration_top_tab_enable", "top_tab_extra", "bottom_tab_type_list",
    "video_tab_cold_start", "is_video_feed_tab_first_request_cold_start",
    "rec_filter_info_list", "ranklist_in_video_tab",
    "new_user_recommend_strategy", "has_video_cache", "novel_filter_room_ids",
    "top_tab_monitor_extra", "is_horizontal_screen",
    "ranklist_in_1col_show_times", "minor_mode_version", "continue_watch_scene",
]

# search_page <- com.dragon.read.rpc.model.GetSearchPageRequest (50 fields)
SEARCH_PAGE_FIELDS: List[str] = [
    "query", "offset", "search_id", "passback", "use_correct", "tab_type",
    "corrected_query", "bookshelf_search_plan", "search_source",
    "search_source_id", "tab_name", "user_is_login", "bookstore_tab",
    "clicked_content", "pad_column_cover", "use_lynx", "count",
    "selected_items", "source_page", "source_book_id", "report_info",
    "client_extra", "ecom_search_source", "is_first_enter_search",
    "ecom_selected_items", "ecom_search_page_version", "client_ab_info",
    "tos_id", "bbox", "tag_name", "line_words_num", "image_url",
    "last_book_id", "last_chapter_id", "last_consume_interval",
    "last_search_page_query", "last_search_page_interval", "from_rs",
    "product_id", "live_room_id", "target_main_id", "biz_config_ctx_infos",
    "video_id", "only_feed", "only_large_card", "seed_product_id",
    "feed_impression_items", "from_half_screen", "last_book_consume_time",
    "search_cur_cue_word", "app_launch_time",
]

# reader full <- com.dragon.read.rpc.model.FullRequest
FULL_FIELDS: List[str] = [
    "item_id", "novel_text_type", "comic_resolution", "unlock_mode",
    "req_type", "book_id", "key_register_ts",
]
# reader batch_full <- com.dragon.read.rpc.model.BatchFullRequest
BATCH_FULL_FIELDS: List[str] = [
    "item_ids", "book_id", "req_type", "novel_text_type", "key_register_ts",
]
# detail <- com.dragon.read.rpc.model.BookDetailRequest
DETAIL_FIELDS: List[str] = [
    "book_id", "category_name", "source", "vs_id_type", "video_series_id",
    "without_video", "book_name", "show_character_module", "from_same_ip",
]


def demo_list_params() -> Dict[str, str]:
    """Reasonable defaults for an anonymous book-list request."""
    return {
        "tab_index": "0",
        "tab_type": "0",
        "offset": "0",
        "stream_count": "10",
        "client_req_type": "1",
    }


def demo_search_params(query: str) -> Dict[str, str]:
    return {
        "query": query,
        "offset": "0",
        "count": "10",
        "tab_type": "0",
        "search_source": "0",
        "user_is_login": "0",
        "use_correct": "1",
    }
